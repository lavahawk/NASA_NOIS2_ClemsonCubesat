# Dynamic World is a 10m near-real-time (NRT) Land Use/Land Cover (LULC) dataset that includes class probabilities and label information for nine classes.
# Dynamic World predictions are available for the Sentinel-2 L1C collection from 2015-06-27 to present. The revisit frequency of Sentinel-2 is between 2-5 days depending on latitude. Dynamic World predictions are generated for Sentinel-2 L1C images with CLOUDY_PIXEL_PERCENTAGE <= 35%. Predictions are masked to remove clouds and cloud shadows using a combination of S2 Cloud Probability, Cloud Displacement Index, and Directional Distance Transform.
# Images in the Dynamic World collection have names matching the individual Sentinel-2 L1C asset names from which they were derived, e.g:
# ee.Image('COPERNICUS/S2/20160711T084022_20160711T084751_T35PKT')
# has a matching Dynamic World image named: ee.Image('GOOGLE/DYNAMICWORLD/V1/20160711T084022_20160711T084751_T35PKT').
# All probability bands except the "label" band collectively sum to 1.
# To learn more about the Dynamic World dataset and see examples for generating composites, calculating regional statistics, and working with the time series, see the Introduction to Dynamic World tutorial series.
# Given Dynamic World class estimations are derived from single images using a spatial context from a small moving window, top-1 "probabilities" for predicted land covers that are in-part defined by cover over time, like crops, can be comparatively low in the absence of obvious distinguishing features. High-return surfaces in arid climates, sand, sunglint, etc may also exhibit this phenomenon.
# To select only pixels that confidently belong to a Dynamic World class, it is recommended to mask Dynamic World outputs by thresholding the estimated "probability" of the top-1 prediction.

# Bands
# Pixel size: 10 meters (all bands)
# Name 	                Min   Max 	Pixel Size 	Description
# water 	            0     1 	10 meters 	Estimated probability of complete coverage by water
# trees 	            0     1 	10 meters 	Estimated probability of complete coverage by trees
# grass 	            0     1 	10 meters 	Estimated probability of complete coverage by grass
# flooded_vegetation 	0  	  1 	10 meters 	Estimated probability of complete coverage by flooded vegetation
# crops 	            0 	  1 	10 meters 	Estimated probability of complete coverage by crops
# shrub_and_scrub 	    0 	  1 	10 meters 	Estimated probability of complete coverage by shrub and scrub
# built 	            0 	  1 	10 meters 	Estimated probability of complete coverage by built
# bare 	                0 	  1 	10 meters 	Estimated probability of complete coverage by bare
# snow_and_ice 	        0 	  1 	10 meters 	Estimated probability of complete coverage by snow and ice
# label 	            0 	  8 	10 meters 	Index of the band with the highest estimated probability

# label Class Table
# Value Color 	    Description
# 0 	#419bdf 	water
# 1 	#397d49 	trees
# 2 	#88b053 	grass
# 3 	#7a87c6 	flooded_vegetation
# 4 	#e49635 	crops
# 5 	#dfc35a 	shrub_and_scrub
# 6 	#c4281b 	built
# 7 	#a59b8f 	bare
# 8 	#b39fe1 	snow_and_ice

import ee
import geemap.core as geemap

# Construct a collection of corresponding Dynamic World and Sentinel-2 for
# inspection. Filter by region and date.
START = ee.Date('2021-04-02')
END = START.advance(1, 'day')

col_filter = ee.Filter.And(
    ee.Filter.bounds(ee.Geometry.Point(20.6729, 52.4305)),
    ee.Filter.date(START, END),
)

dw_col = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filter(col_filter)
s2_col = ee.ImageCollection('COPERNICUS/S2_HARMONIZED');

# Link DW and S2 source images.
linked_col = dw_col.linkCollection(s2_col, s2_col.first().bandNames());

# Get example DW image with linked S2 image.
linked_image = ee.Image(linked_col.first())

# Create a visualization that blends DW class label with probability.
# Define list pairs of DW LULC label and color.
CLASS_NAMES = [
    'water',
    'trees',
    'grass',
    'flooded_vegetation',
    'crops',
    'shrub_and_scrub',
    'built',
    'bare',
    'snow_and_ice',
]

VIS_PALETTE = [
    '419bdf',
    '397d49',
    '88b053',
    '7a87c6',
    'e49635',
    'dfc35a',
    'c4281b',
    'a59b8f',
    'b39fe1',
]

# Create an RGB image of the label (most likely class) on [0, 1].
dw_rgb = (
    linked_image.select('label')
    .visualize(min=0, max=8, palette=VIS_PALETTE)
    .divide(255)
)

# Get the most likely class probability.
top1_prob = linked_image.select(CLASS_NAMES).reduce(ee.Reducer.max())

# Create a hillshade of the most likely class probability on [0, 1]
top1_prob_hillshade = ee.Terrain.hillshade(top1_prob.multiply(100)).divide(255)

# Combine the RGB image with the hillshade.
dw_rgb_hillshade = dw_rgb.multiply(top1_prob_hillshade)

# Display the Dynamic World visualization with the source Sentinel-2 image.
m = geemap.Map()
m.set_center(20.6729, 52.4305, 12)
m.add_layer(
    linked_image,
    {'min': 0, 'max': 3000, 'bands': ['B4', 'B3', 'B2']},
    'Sentinel-2 L1C',
)
m.add_layer(
    dw_rgb_hillshade,
    {'min': 0, 'max': 0.65},
    'Dynamic World V1 - label hillshade',
)