import os
import ee
import json
import requests
import numpy as np
import pandas as pd
import datetime as dt

service_account = 'fire-water-chart@appspot.gserviceaccount.com'
credentials = ee.ServiceAccountCredentials(service_account, 'privatekey.json')
ee.Initialize(credentials)

def serializer(df_pre, df_fire):

    return json.loads(pd.merge(df_fire, df_pre, how='left', on='date').to_json(orient='records'))

def get_geometry(iso, adm1=None):
    """
    Return a geometry as a GeoJSON from geostore.

    Parameters
    ----------
        iso : str
            Country iso code.
        adm1 : int or bool, optional
            Admin 1 code. Must be non-negative.

    Returns
    -------
        geometry : GeoJSON
            GeoJSON object describing the geometry.

    Examples
    --------
    >>> get_geometry('BRA', 22)
    {'crs': {},
    'features': [{'geometry': {'coordinates': [[[[-62.8922, -12.8601],
        [-62.8921, -12.8588],
        [-62.9457, -12.8571],
        ...]]],
        'type': 'MultiPolygon'},
    'properties': None,
    'type': 'Feature'}],
    'type': 'FeatureCollection'}
    """
    if adm1:
        if adm1 < 0:
            raise ValueError("Code number %s must be non-negative." % adm1)
        url = f'https://api.resourcewatch.org/v2/geostore/admin/{iso}/{adm1}'

    else:
        url = f'https://api.resourcewatch.org/v2/geostore/admin/{iso}'

    r = requests.get(url)
    geometry = r.json().get('data').get('attributes').get('geojson')

    return geometry

def get_dates(date_text=None):
    """
    Return relevant dates

    Parameters
    ----------
        date_text : str, optional
            String with the last date. Format should be YYYY-MM-DD.

    Returns
    -------
        dates : DatetimeIndex
            List of dates.
        start_date : Timestamp
            First date for moving window computation.
        end_date : Timestamp
            Last date for moving window computation.
        start_year_date : Timestamp
            First day of the 1 year range.    
    """
    if date_text:
        try:
            dt.datetime.strptime(date_text, '%Y-%m-%d')
        except ValueError:
            raise ValueError("Incorrect data format, should be YYYY-MM-DD")
        date = pd.to_datetime(date_text)

    else:
        date = pd.to_datetime('today').normalize()

    nDays_year =  len(pd.date_range(date.replace(month=1, day=1) , date.replace(month=12, day=31) ,freq='D'))
    start_year_date = date - dt.timedelta(days=nDays_year)
    start_date = date - dt.timedelta(days=nDays_year+61)
    end_date = date + dt.timedelta(days=61)
    dates = pd.date_range(start_date, end_date, freq='D').astype(str)

    return dates, start_date, date, end_date, start_year_date

def nestedMappedReducer(featureCol, imageCol):
    """
    Computes mean values for each geometry in a FeatureCollection and each image in an ImageCollection.
    To prevent "Computed value is too large" error we will map reduceRegion() over the FeatureCollection instead of using reduceRegions().

    Parameters
    ----------
        featureCol : ee.FeatureCollection
            FeatureCollection with the geometries that we want to intersect with.
        imageCol : ee.ImageCollection
            ImageCollection with a time series of images.

    Returns
    -------
        featureCol : ee.FeatureCollection
            FeatureCollection with the mean values for each geometry and date.  
    """
    def mapReducerOverImgCol(feature):
        def imgReducer(image):
            return ee.Feature(feature.geometry().centroid(100),
                image.reduceRegion(
                    geometry = feature.geometry(),
                    reducer = ee.Reducer.mean(),
                    tileScale = 10,
                    maxPixels = 1e+13,
                    bestEffort = True 
                )).set({'date': image.date().format("YYYY-MM-dd")}).copyProperties(feature)

        return imageCol.map(imgReducer)

    return featureCol.map(mapReducerOverImgCol).flatten()

def fire_water_chart(request):

    # Set CORS headers for the preflight request
    if request.method == 'OPTIONS':
        # Allows GET requests from any origin with the Content-Type
        # header and caches preflight response for an 3600s
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }

        return ('', 204, headers)

    # Set CORS headers for the main request
    headers = {
        'Access-Control-Allow-Origin': '*'
    }

    request_json = request.get_json()
    
    # Get geometry as GeoJSON from geostore
    geometry = get_geometry(request_json['iso'], request_json['adm1'])

    # Convert geometry to ee.Geometry
    aoi = ee.Geometry(geometry.get('features')[0].get('geometry'))

    # Get relevant dates
    dates, start_date, date, end_date, start_year_date = get_dates(request_json['date_text'])

    # Read ImageCollection
    dataset = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY') \
        .filter(ee.Filter.date(start_date.strftime('%Y-%m-%d'), (end_date + dt.timedelta(days=1)).strftime('%Y-%m-%d'))).filterBounds(aoi)
    chirps = dataset.select('precipitation')

    # Get mean precipitation values over time
    count = chirps.size()
    data = nestedMappedReducer(ee.FeatureCollection(geometry.get('features')), chirps).toList(count).getInfo()
    df_pre = pd.DataFrame(map(lambda x: x.get('properties'), data))

    # VIIRS fire alerts
    confidence = 'h' #'n', 'l'

    if request_json['adm1']:
        query =(f"SELECT alert__date, SUM(alert__count) AS alert__count \
                FROM data WHERE iso = \'{request_json['iso']}\' AND adm1::integer = {request_json['adm1']} AND confidence__cat = \'{confidence}\' AND alert__date >= \'{start_date}\' AND alert__date <= \'{end_date}\' \
                GROUP BY iso, adm1, alert__date, confidence__cat \
                ORDER BY alert__date"
        )
    else:
        query =(f"SELECT alert__date, SUM(alert__count) AS alert__count \
                FROM data WHERE iso = \'{request_json['iso']}\' AND confidence__cat = \'{confidence}\' AND alert__date >= \'{start_date}\' AND alert__date <= \'{end_date}\' \
                GROUP BY iso, alert__date, confidence__cat \
                ORDER BY alert__date"
        )

    url = f"https://data-api.globalforestwatch.org/dataset/gadm__viirs__adm2_daily_alerts/latest/query/json"

    sql = {"sql": query}
    r = requests.get(url, params=sql)

    data = r.json().get('data')
    if data: 
        df_fire = pd.DataFrame.from_dict(pd.json_normalize(data))
        # Fill missing dates with 0
        df_fire = df_fire.set_index('alert__date').reindex(dates, fill_value=0).reset_index().rename(columns={'index': 'alert__date'})
        df_fire.rename(columns = {'alert__date': 'date', 'alert__count': 'fire'}, inplace= True)
    else:
        df_fire = pd.DataFrame({"date": dates, 'fire': 0})

    # Moving averages
    # 1 week moving average
    df_pre['precipitation_w'] = df_pre[['date', 'precipitation']].rolling(window=7, center=True).mean()
    df_fire['fire_w'] = df_fire[['date', 'fire']].rolling(window=7, center=True).mean()
    # 2 month moving average
    df_pre['precipitation_2m'] = df_pre[['date', 'precipitation']].rolling(window=61, center=True).mean()
    df_fire['fire_2m'] = df_fire[['date', 'fire']].rolling(window=61, center=True).mean()
    # take current year days
    df_pre = df_pre[(df_pre['date'] >= start_year_date.strftime('%Y-%m-%d')) & (df_pre['date'] <= date.strftime('%Y-%m-%d'))]
    df_fire = df_fire[(df_fire['date'] >= start_year_date.strftime('%Y-%m-%d')) & (df_fire['date'] <= date.strftime('%Y-%m-%d'))]

    return (json.dumps(serializer(df_pre, df_fire)), 200, headers)
