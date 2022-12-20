import os
import requests
import multiprocessing
import time
import urllib
import numpy as np
import pandas as pd
from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw
import io
import json
import math
import ee_collection_specifics
from google.cloud import storage
from dotenv import load_dotenv
from pathlib import Path
import ipyleaflet as ipyl
import folium
import ffmpeg
import ee


def resize_image(img, y_pixels=20):
    wpercent = y_pixels / float(img.size[1])
    return img.resize((int(img.size[0] * wpercent), y_pixels), Image.ANTIALIAS)


def add_white_rectangle(img, y_pixels=20):
    np_img = np.array(img)
    np_img[np_img.shape[0] - y_pixels :, :, :] = 255
    return Image.fromarray(np_img.astype(np.uint8))


def add_logo(img, logo_path, y_pixels=20):
    logo = Image.open(logo_path).convert("RGBA")
    logo = resize_image(logo, y_pixels=y_pixels)
    x_img, y_img = img.size
    x, y = logo.size
    img.paste(logo, (0, y_img - y, x, y_img), logo)

    return img


def add_year(img, year=2000, y_pixels=20):
    np_img = np.array(img)
    np_img[:y_pixels, : int(y_pixels * 2.5), :] = 255
    img = Image.fromarray(np_img.astype(np.uint8))

    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("../data/Roboto-Regular.ttf", y_pixels - 4)
    draw.text((int(y_pixels / 5), 0), str(year), (0, 0, 0), font=font)

    return img


class Composite:
    def __init__(self, geometry, startDate, stopDate, collection):
        """
        Class used to get composites from Earth Engine
        Parameters
        ----------
        geometry : GeoJSON
            GeoJSON with a polygon.
        startDate : string
        stopDate : string
        collection: string
            Name of a collection.

        """

        self.geometry = geometry
        self.startDate = startDate
        self.stopDate = stopDate
        self.collection = collection
        self.scale = ee_collection_specifics.scales(self.collection)
        self.color = "#2BA4A0"
        self.style_function = lambda x: {
            "fillOpacity": 0.0,
            "weight": 4,
            "color": self.color,
        }

        # Earth Engine tile URL
        self.ee_tiles = "https://earthengine.googleapis.com/map/{mapid}/{{z}}/{{x}}/{{y}}?token={token}"

        self.bucket = "skydipper_materials"

        # Area of Interest
        self.region = (
            self.geometry.get("features")[0].get("geometry").get("coordinates")
        )
        self.polygon = ee.Geometry.Polygon(self.region)
        self.centroid = self.polygon.centroid().getInfo().get("coordinates")[::-1]
        self.locations = list(map(tuple, list(map(lambda x: x[::-1], self.region[0]))))
        self.bbox = self.polygon.bounds().getInfo().get("coordinates")[0]
        self.bounds = [self.bbox[0][::-1], self.bbox[2][::-1]]

        # Image Collection
        self.image_collection = ee_collection_specifics.ee_collections(self.collection)

        # Image Visualization parameters
        self.vis = ee_collection_specifics.ee_vis(self.collection)

        # Saving parameters
        self.visSave = {
            "dimensions": 1024,
            "format": "png",
            "crs": "EPSG:3857",
            "region": self.region,
        }

    def read_composite(self):
        ## Composite
        self.image = ee_collection_specifics.Composite(self.collection)(
            self.image_collection, self.startDate, self.stopDate, self.scale
        )

        self.image = self.image.visualize(**self.vis)

    def save_composite_as_png(self, path, file_name):
        url = self.image.getThumbURL(self.visSave)

        if os.path.exists(path + f"{file_name}.png"):
            os.remove(path + f"{file_name}.png")

        urllib.request.urlretrieve(url, path + f"{file_name}.png")

    def display_composite_ipyleaflet(self, zoom=10):
        image = self.image.clip(ee.Geometry(self.polygon))
        mapid = image.getMapId()
        tiles_url = self.ee_tiles.format(**mapid)

        tile_layer = ipyl.TileLayer(
            url=tiles_url,
            layers="collection",
            format="image/png",
            name=self.collection,
            opacity=1,
        )

        polygon = ipyl.Polygon(
            locations=self.locations, color=self.color, fill_opacity=0.0, name="AoI"
        )

        m = ipyl.Map(center=tuple(self.centroid), zoom=zoom)

        m.add_layer(tile_layer)
        m.add_layer(polygon)

        control = ipyl.LayersControl(position="topright")
        m.add_control(control)
        m.add_control(ipyl.FullScreenControl())
        return m

    def display_composite_folium(self):
        image = self.image.clip(ee.Geometry(self.polygon))
        mapid = image.getMapId()
        tiles_url = self.ee_tiles.format(**mapid)

        m = folium.Map(location=self.centroid)
        m.fit_bounds(self.bounds)

        folium.TileLayer(
            tiles=tiles_url,
            attr="Google Earth Engine",
            overlay=True,
            name=self.collection,
        ).add_to(m)

        folium.GeoJson(
            data=json.dumps(self.geometry),
            style_function=self.style_function,
            name="AoI",
        ).add_to(m)

        m.add_child(folium.LayerControl())

        return m


class Animation:
    def __init__(self, geometry, start_year, stop_year, instrument):
        """
        Class used to get animations from Earth Engine
        Parameters
        ----------
        geometry : GeoJSON
            GeoJSON with a polygon.
        start_year : int
        stop_year : int
        instrument: string
            Name of a instrument (Landsat or Sentinel).
        """

        self.geometry = geometry
        self.start_year = start_year
        self.stop_year = stop_year
        self.instrument = instrument

        # GCS parameters
        self.bucket = "skydipper_materials"

        self.env_path = Path("..") / ".env"
        load_dotenv(dotenv_path=self.env_path)
        self.privatekey_path = os.getenv("PRIVATEKEY_PATH")

        # Area of Interest
        self.region = (
            self.geometry.get("features")[0].get("geometry").get("coordinates")
        )
        self.polygon = ee.Geometry.Polygon(self.region)
        self.centroid = self.polygon.centroid().getInfo().get("coordinates")[::-1]
        self.bbox = self.polygon.bounds().getInfo().get("coordinates")[0]
        self.bounds = [self.bbox[0][::-1], self.bbox[2][::-1]]

    def visFun(self, img, vis):
        """
        Define a function to convert an image to an RGB visualization image and copy
        properties from the original image to the RGB image.
        """
        return img.visualize(**vis).copyProperties(img, img.propertyNames())

    def create_collection(self, scale=None):

        years = np.arange(self.start_year, self.stop_year + 1)

        dic = ee_collection_specifics.date_range(self.instrument)
        years_range = list(map(list, list(dic.values())))
        collections = list(dic.keys())

        images = []
        for year in years:
            n = 0
            in_range = False
            for sub_years in years_range:
                if year in sub_years:
                    in_range = True
                    break
                n = +1

            if not in_range:
                raise ValueError(f"Year out of range.")

            collection = collections[n]

            if scale:
                scale = scale
            else:
                scale = ee_collection_specifics.scales(collection)

            # Image Collection
            image_collection = ee_collection_specifics.ee_collections(collection)

            # Image Visualization parameters
            vis = ee_collection_specifics.ee_vis(collection)

            step_range = ee_collection_specifics.step_range(collection)

            startDate = ee.Date(str(year + step_range[0]) + "-12-31")
            stopDate = ee.Date(str(year + step_range[1]) + "-12-31")

            image = ee_collection_specifics.Composite(collection)(
                image_collection, startDate, stopDate, scale, self.polygon
            )

            # convert image to an RGB visualization
            images.append(self.visFun(image, vis))

        return images

    def video_as_array(self, dimensions=512, scale=None):

        images = self.create_collection(scale=scale)

        visSave = {
            "dimensions": dimensions,
            "format": "png",
            "crs": "EPSG:3857",
            "region": self.region,
        }

        for n, image in enumerate(images):
            print(f"Image number: {str(n)}")
            image = ee.Image(image)

            url = image.getThumbURL(visSave)
            response = requests.get(url)
            array = np.array(Image.open(io.BytesIO(response.content)))

            array = array.reshape((1,) + array.shape)

            # Add alpha channel if needed
            if array.shape[3] == 3:
                array = np.append(
                    array,
                    np.full((array.shape[0], array.shape[1], array.shape[2], 1), 255),
                    axis=3,
                )

            if n == 0:
                arrays = array
            else:
                arrays = np.append(arrays, array, axis=0)

        self.images = arrays
        return self.images

    def video_add_elements(self, logo_path, y_pixels):

        years = np.arange(self.start_year, self.stop_year + 1)

        for n, image in enumerate(self.images):
            img = Image.fromarray(image.astype(np.uint8))
            img = add_white_rectangle(img, y_pixels=y_pixels)
            img = add_logo(img, logo_path, y_pixels=y_pixels)
            img = add_year(img, year=str(years[n]), y_pixels=y_pixels)

            self.images[n, :] = np.array(img)
        return self.images

    def create_movie_from_array(
        self, output_file, output_format="webm", framerate=None
    ):
        if not isinstance(self.images, np.ndarray):
            self.images = np.asarray(self.images)

        n, height, width, channels = self.images.shape

        # Height and width should be divisible by 2
        if height % 2 == 1:
            height = math.floor(height / 2.0) * 2
        if width % 2 == 1:
            width = math.floor(width / 2.0) * 2

        self.images = self.images[:, :height, :width, :]

        if framerate == None:
            framerate = n

        if output_format == "mp4":
            process = (
                ffmpeg.input(
                    "pipe:",
                    format="rawvideo",
                    pix_fmt="rgb24",
                    s="{}x{}".format(width, height),
                )
                .output(output_file, pix_fmt="yuv420p", vcodec="libx264", r=framerate)
                .overwrite_output()
                .run_async(pipe_stdin=True, overwrite_output=True)
            )

        if output_format == "mov":
            process = (
                ffmpeg.input(
                    "pipe:",
                    format="rawvideo",
                    pix_fmt="rgba",
                    s="{}x{}".format(width, height),
                )
                .output(output_file, vcodec="png", r=framerate)
                .overwrite_output()
                .run_async(pipe_stdin=True, overwrite_output=True)
            )

        if output_format == "webm":
            process = (
                ffmpeg.input(
                    "pipe:",
                    format="rawvideo",
                    pix_fmt="rgba",
                    s="{}x{}".format(width, height),
                )
                .output(
                    output_file,
                    **{"auto-alt-ref": 0, "qmin": 0, "qmax": 50, "crf": 5, "b:v": "1M"},
                    r=framerate,
                )
                .overwrite_output()
                .run_async(pipe_stdin=True, overwrite_output=True)
            )

        if output_format == "mp4":
            self.images = self.images[:, :, :, :3]

        for frame in self.images:
            process.stdin.write(frame.astype(np.uint8).tobytes())
        process.stdin.close()
        process.wait()

    def upload_blob(self, source_file_name, destination_blob_name):
        """Uploads a file to the bucket."""
        storage_client = storage.Client.from_service_account_json(self.privatekey_path)
        bucket = storage_client.bucket(self.bucket)
        blob = bucket.blob(destination_blob_name)

        blob.upload_from_filename(source_file_name)

        print("File {} uploaded to {}.".format(source_file_name, destination_blob_name))

    def display_animation(self, url):
        m = ipyl.Map(center=tuple(self.centroid), zoom=12)

        video = ipyl.VideoOverlay(url=url, bounds=tuple(list(map(tuple, self.bounds))))

        m.add_layer(video)
        m.add_control(ipyl.FullScreenControl())

        return m


class Animation_old:
    def __init__(self, geometry, start_year, stop_year, instrument):
        """
        Class used to get animations from Earth Engine
        Parameters
        ----------
        geometry : GeoJSON
            GeoJSON with a polygon.
        start_year : int
        stop_year : int
        instrument: string
            Name of a instrument (Landsat or Sentinel).
        """

        self.geometry = geometry
        self.start_year = start_year
        self.stop_year = stop_year
        self.instrument = instrument
        self.color = "#2BA4A0"
        self.style_function = lambda x: {
            "fillOpacity": 0.0,
            "weight": 4,
            "color": self.color,
        }

        # Earth Engine tile URL
        self.ee_tiles = "https://earthengine.googleapis.com/map/{mapid}/{{z}}/{{x}}/{{y}}?token={token}"

        # GCS parameters
        self.bucket = "skydipper_materials"
        self.prefix = "mongabay"

        self.env_path = Path("..") / ".env"
        load_dotenv(dotenv_path=self.env_path)
        self.privatekey_path = os.getenv("PRIVATEKEY_PATH")

        # Area of Interest
        self.region = (
            self.geometry.get("features")[0].get("geometry").get("coordinates")
        )
        self.polygon = ee.Geometry.Polygon(self.region)
        self.centroid = self.polygon.centroid().getInfo().get("coordinates")[::-1]
        self.locations = list(map(tuple, list(map(lambda x: x[::-1], self.region[0]))))
        self.bbox = self.polygon.bounds().getInfo().get("coordinates")[0]
        self.bounds = [self.bbox[0][::-1], self.bbox[2][::-1]]

    def visFun(self, img, vis):
        """
        Define a function to convert an image to an RGB visualization image and copy
        properties from the original image to the RGB image.
        """
        return img.visualize(**vis).copyProperties(img, img.propertyNames())

    def create_collection(self, scale=None):

        years = np.arange(self.start_year, self.stop_year + 1)

        dic = ee_collection_specifics.date_range(self.instrument)
        years_range = list(map(list, list(dic.values())))
        collections = list(dic.keys())

        image_list = []
        for year in years:
            n = 0
            in_range = False
            for sub_years in years_range:
                if year in sub_years:
                    in_range = True
                    break
                n = +1

            if not in_range:
                raise ValueError(f"Year out of range.")

            collection = collections[n]

            if scale:
                scale = scale
            else:
                scale = ee_collection_specifics.scales(collection)

            # Image Collection
            image_collection = ee_collection_specifics.ee_collections(collection)

            # Image Visualization parameters
            vis = ee_collection_specifics.ee_vis(collection)

            step_range = ee_collection_specifics.step_range(collection)

            startDate = ee.Date(str(year + step_range[0]) + "-12-31")
            stopDate = ee.Date(str(year + step_range[1]) + "-12-31")

            image = ee_collection_specifics.Composite(collection)(
                image_collection, startDate, stopDate, scale, self.polygon
            )

            # convert image to an RGB visualization
            image_list.append(self.visFun(image, vis))

        return image_list

    def animated_ThumbURL(self, frames_per_second=4, dimensions=256, scale=None):
        rgbVis = ee.ImageCollection(self.create_collection(scale=scale))

        # Define arguments for animation function parameters.
        videoArgs = {
            "dimensions": dimensions,
            "region": self.polygon,
            "framesPerSecond": frames_per_second,
            "crs": "EPSG:3857",
            "tileScale": 10,
            "pixels": 1e13,
        }

        # Print a URL that will produce the animation when accessed.
        url = rgbVis.getVideoThumbURL(videoArgs)

        # Raise error if image computation is too large
        def response(url):
            r = requests.get(url)
            return r.text

        # Start response as a process
        p = multiprocessing.Process(target=response, name="Response", args=(url,))
        p.start()

        # Wait 5 seconds for foo
        time.sleep(3)

        # Terminate foo
        p.terminate()

        # Cleanup
        p.join()

        if p.exitcode >= 0:
            raise ValueError(
                response(url).split("(")[0][:-1]
                + ". Try specifying a larger 'scale' parameter."
            )

        return url

    def rename_blob(self, bucket_name, prefix, privatekey_path):
        """Renames a blob."""
        storage_client = storage.Client.from_service_account_json(privatekey_path)
        bucket = storage_client.get_bucket(bucket_name)

        base_url = f"https://storage.cloud.google.com/{bucket_name}/"

        # List of files
        blobs = bucket.list_blobs(prefix="mongabay")

        # Rename '.mp4' files
        new_names = []
        for blob in blobs:
            blob_name = blob.name

            if ("ee-export-video" in blob_name) and (blob_name[-4:] == ".mp4"):

                new_name = (
                    blob_name.split("ee-export-video")[0]
                    + f"video_{str(int(time.time()))}.mp4"
                )

                blob = bucket.blob(blob_name)
                new_blob = bucket.rename_blob(blob, new_name)

                print("Blob {} has been renamed to {}".format(blob_name, new_name))

                new_names.append(new_name)

        return list(map(lambda x: base_url + x, new_names))

    def export_video_to_GCS(self, frames_per_second=4, dimensions=256, scale=None):
        rgbVis = ee.ImageCollection(self.create_collection(scale=scale))

        task = ee.batch.Export.video.toCloudStorage(
            collection=rgbVis,
            description="export_video_to_GCS",
            bucket=self.bucket,
            fileNamePrefix="mongabay/movie_test/",
            dimensions=dimensions,
            framesPerSecond=frames_per_second,
            region=self.region,
            maxPixels=1e10,
        )
        task.start()

        # Monitoring video export task
        status = task.status().get("state")
        while not task.status().get("state") == "COMPLETED":
            print("Temporal status: ", task.status().get("state"))

            time.sleep(10)

        print("Final status: ", task.status().get("state"))

        # Rename exported file
        self.file_name = self.rename_blob(
            self.bucket, self.prefix, self.privatekey_path
        )[0]

    def display_video(self, zoom=12):
        # Display movie on map
        m = ipyl.Map(center=tuple(self.centroid), zoom=zoom)

        video = ipyl.VideoOverlay(
            url=self.file_name, bounds=tuple(list(map(tuple, self.bounds)))
        )

        polygon = ipyl.Polygon(
            locations=self.locations, color=self.color, fill_opacity=0.0, name="AoI"
        )

        m.add_layer(video)
        m.add_layer(polygon)

        return m

    def video_as_array(self, dimensions=256, scale=None):

        visSave = {
            "dimensions": dimensions,
            "format": "png",
            "crs": "EPSG:3857",
            "region": self.region,
        }

        images = self.create_collection(scale=scale)

        for n, image in enumerate(images):
            print(f"Image number: {str(n)}")
            image = ee.Image(image)

            url = image.getThumbURL(visSave)
            response = requests.get(url)
            array = np.array(Image.open(io.BytesIO(response.content)))

            array = array.reshape((1,) + array.shape)

            if n == 0:
                arrays = array
            else:
                arrays = np.append(arrays, array, axis=0)

        return arrays
