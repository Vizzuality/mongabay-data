from ee_satellite_imagery import Animation
import json
import os
import ee

service_account = 'gee-tiles@skydipper-196010.iam.gserviceaccount.com'
credentials = ee.ServiceAccountCredentials(service_account, 'privatekey.json')
ee.Initialize(credentials)

def serializer(url):

    return {
        'download_url': url
    }

def animation(request):
    request = request.get_json()
    
    animation = Animation(geometry=request['geometry'], start_year = request['start_year'], stop_year = request['stop_year'], instrument = request['instrument'])
    
    # Numpy array
    animation.video_as_array(dimensions=request['dimensions'])
    animation.video_add_elements(logo_path='mongabay-horizontal.jpg', y_pixels=20)

    # Create animations from a Numpy Array
    animation.create_movie_from_array('/tmp/movie.mp4', output_format='mp4')
    
    # Upload animation to Google cloud storage
    print('Uploadong animation to Google cloud storage')
    source_file_name = '/tmp/movie.mp4'
    destination_blob_name = 'movie-tiles/mongabay/movie.mp4'
    animation.upload_blob(source_file_name, destination_blob_name)

    url = "https://storage.cloud.google.com/skydipper_materials/movie-tiles/mongabay/movie.mp4"
    
    # Remove file from local directory
    os.remove('/tmp/movie.mp4')

    return json.dumps(serializer(url))