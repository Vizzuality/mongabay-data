"""
Information on Earth Engine collections stored here (e.g. bands, collection ids, etc.)
"""
import numpy as np

def ee_collections(collection):
    """
    Earth Engine image collection names
    """
    dic = {
        'Landsat4': 'LANDSAT/LT04/C01/T1_SR',
        'Landsat5': 'LANDSAT/LT05/C01/T1_SR',
        'Landsat7': 'LANDSAT/LE07/C01/T1_SR',
        'Landsat457': ['LANDSAT/LT04/C01/T1_SR','LANDSAT/LT05/C01/T1_SR', 'LANDSAT/LE07/C01/T1_SR'],
        'Landsat8': 'LANDSAT/LC08/C01/T1_SR',
        'Sentinel2': 'COPERNICUS/S2'
    }
    
    return dic[collection]

def ee_vis(collection):
    """
    Earth Engine image visualization parameters
    """
    dic = {
        'Landsat4': {'min':0,'max':3000, 'gamma':1.4, 'bands':['B3', 'B2', 'B1']},
        'Landsat5': {'min':0,'max':3000, 'gamma':1.4, 'bands':['B3', 'B2', 'B1']},
        'Landsat7': {'min':0,'max':3000, 'gamma':1.4, 'bands':['B3', 'B2', 'B1']},
        'Landsat457': {'min':0,'max':3000, 'gamma':1.4, 'bands':['B3', 'B2', 'B1']},
        'Landsat8': {'min':0,'max':3000, 'gamma':1.4, 'bands':['B4', 'B3', 'B2']},
        'Sentinel2': {'min':0,'max':0.25, 'bands':['B4', 'B3', 'B2']},
    }
    
    return dic[collection]

def scales(collection):
    """
    Earth Engine image visualization parameters
    """
    dic = {
        'Landsat4': 30,
        'Landsat5': 30,
        'Landsat7': 30,
        'Landsat457': 30,
        'Landsat8': 30,
        'Sentinel2': 10,
    }
    
    return dic[collection]

def steps(collection):
    """
    Earth Engine image visualization parameters
    """
    dic = {
        'Landsat4': 4,
        'Landsat5': 4,
        'Landsat7': 4,
        'Landsat457': 4,
        'Landsat8': 1,
        'Sentinel2': 1,
    }
    
    return dic[collection]


def step_range(collection):
    """
    Earth Engine image visualization parameters
    """
    dic = {
        'Landsat457': [-2,2],
        'Landsat8': [-1,0],
        'Sentinel2': [-1,0],
    }
    
    return dic[collection]

def date_range(instrument):
    """
    Instruments data ranges
    """
    dic = {
        'Landsat': {'Landsat457': np.arange(1985, 2012+1), 'Landsat8': np.arange(2013, 2019+1)},
        'Sentinel': {'Sentinel2': np.arange(2016, 2019+1)}
    }
    
    return dic[instrument]

""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
import ee

## Lansat 4, 5 and 7 Cloud Free Composite
def CloudMaskL457(image):
    qa = image.select('pixel_qa')
    #If the cloud bit (5) is set and the cloud confidence (7) is high
    #or the cloud shadow bit is set (3), then it's a bad pixel.
    cloud = qa.bitwiseAnd(1 << 5).And(qa.bitwiseAnd(1 << 7)).Or(qa.bitwiseAnd(1 << 3))
    #Remove edge pixels that don't occur in all bands
    mask2 = image.mask().reduce(ee.Reducer.min())
    return image.updateMask(cloud.Not()).updateMask(mask2)

def CloudFreeCompositeL(Collection_id, startDate, stopDate, scale = None, geom=None):
    ## Define your collection
    collection = ee.ImageCollection(Collection_id)

    ## Filter 
    collection = collection.filterDate(startDate,stopDate)\
            .map(CloudMaskL457)
    
    if geom:
        collection = collection.filterBounds(geom)

    ## Composite
    composite = collection.median()
    
    ## Choose the scale
    if scale:
        composite =  composite.reproject(crs='EPSG:4326', scale=scale)
    
    return composite

## Lansat 4 + 5 + 7 Cloud Free Composite
def CloudFreeCompositeL457(Collection_id, startDate, stopDate, scale = None, geom=None):
    ## Define your collections
    collection_L4 = ee.ImageCollection(Collection_id[0])
    collection_L5 = ee.ImageCollection(Collection_id[1])
    collection_L7 = ee.ImageCollection(Collection_id[2])

    ## Filter 
    collection_L4 = collection_L4.filterDate(startDate,stopDate).map(CloudMaskL457)
    collection_L5 = collection_L5.filterDate(startDate,stopDate).map(CloudMaskL457)
    collection_L7 = collection_L7.filterDate(startDate,stopDate).map(CloudMaskL457)
    
    ## merge collections
    collection = collection_L4.merge(collection_L5).merge(collection_L7)
    
    if geom:
        collection = collection.filterBounds(geom)

    ## Composite
    composite = collection.median()
    
    ## Choose the scale
    if scale:
        composite =  composite.reproject(crs='EPSG:4326', scale=scale)
    
    return composite

## Lansat 8 Cloud Free Composite
def maskL8sr(image):  
    # Bits 3 and 5 are cloud shadow and cloud, respectively.
    # Get the pixel QA band.
    qa = image.select('pixel_qa');
    # Both flags should be set to zero, indicating clear conditions.
    mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 5).eq(0))
    return image.updateMask(mask)

def CloudFreeCompositeL8(Collection_id, startDate, stopDate, scale = None, geom = None):
    ## Define your collection
    collection = ee.ImageCollection(Collection_id)

    ## Filter 
    collection = collection.filterDate(startDate,stopDate).map(maskL8sr)
    
    if geom:
        collection = collection.filterBounds(geom)

    ## Composite
    composite = collection.median()
    
    ## Choose the scale
    if scale:
        composite =  composite.reproject(crs='EPSG:4326', scale=scale)
    
    return composite

## Sentinel 2 Cloud Free Composite
def CloudMaskS2(image):
    """
    European Space Agency (ESA) clouds from 'QA60', i.e. Quality Assessment band at 60m
    parsed by Nick Clinton
    """
    qa = image.select('QA60')

    # Bits 10 and 11 are clouds and cirrus, respectively.
    cloudBitMask = int(2**10)
    cirrusBitMask = int(2**11)

    # Both flags set to zero indicates clear conditions.
    mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(\
            qa.bitwiseAnd(cirrusBitMask).eq(0))

    return image.updateMask(mask).divide(10000)

def CloudFreeCompositeS2(Collection_id, startDate, stopDate, scale = None, geom = None):
    ## Define your collection
    collection = ee.ImageCollection(Collection_id)

    ## Filter 
    collection = collection.filterDate(startDate,stopDate)\
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))\
            .map(CloudMaskS2)
    
    if geom:
        collection = collection.filterBounds(geom)

    ## Composite
    composite = collection.median()
    
    ## Choose the scale
    if scale:
        composite =  composite.reproject(crs='EPSG:4326', scale=scale)
    
    return composite

""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

def Composite(collection):
    dic = {
        'Landsat4': CloudFreeCompositeL,
        'Landsat5': CloudFreeCompositeL,
        'Landsat7': CloudFreeCompositeL,
        'Landsat457': CloudFreeCompositeL457,
        'Landsat8': CloudFreeCompositeL8,
        'Sentinel2': CloudFreeCompositeS2,
    }
    
    return dic[collection]
