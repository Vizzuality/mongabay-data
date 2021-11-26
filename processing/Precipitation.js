
var gadm36 = ee.FeatureCollection('projects/wri-datalab/gadm36')

var dataset = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
                  .filter(ee.Filter.date('2021-10-20', '2021-10-23'));
var chirps = dataset.select('precipitation');

// Select AOI
var iso = "ESP";
var aoi = gadm36
  .filterMetadata("iso", "equals", iso);

// Get last image
//var chirps=chirps.limit(1, 'system:time_start', false).first()

//var chirps = chirps.clip(aoi.geometry());

var chirps = chirps.map(function(image) {
    return image.clip(aoi.geometry());
});

var chirpsVis = {
    min: 1.0,
    max: 17.0,
    palette: ['001137', '0aab1e', 'e7eb05', 'ff4a2d', 'e90000'],
  };
  
  Map.setCenter(-3.654, 40.474, 6);
  Map.addLayer(chirps, chirpsVis, 'Precipitation');