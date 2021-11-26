import ee 
from ee_plugin import Map 


gadm36 = ee.FeatureCollection('projects/wri-datalab/gadm36')

dataset = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY') \
                  .filter(ee.Filter.date('2021-10-20', '2021-10-23'))
chirps = dataset.select('precipitation')

# Select AOI
iso = "ESP"
aoi = gadm36 \
  .filterMetadata("iso", "equals", iso)

# Get last image
#chirps=chirps.limit(1, 'system:time_start', False).first()

#chirps = chirps.clip(aoi.geometry())


def func_iul(image):
    return image.clip(aoi.geometry())

chirps = chirps.map(func_iul)




chirpsVis = {
    'min': 1.0,
    'max': 17.0,
    'palette': ['001137', '0aab1e', 'e7eb05', 'ff4a2d', 'e90000'],
  }

  Map.setCenter(-3.654, 40.474, 6)
  Map.addLayer(chirps, chirpsVis, 'Precipitation')
