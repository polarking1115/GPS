import math
import unittest
import map_config

class MapValidation(unittest.TestCase):
    def test_overlay_roundtrip(self):
        config={'center':[34.75,127.75],'zoom':17,'basemap':'satellite','overlay':{'image':'/assets/plan.png','bounds':[[34.74,127.74],[34.76,127.76]],'rotation':30,'opacity':.6}}
        self.assertEqual(map_config.outdoor_map(config),config)
    def test_invalid_images_bounds_numbers(self):
        for patch in [{'center':[True,127]},{'center':[math.nan,127]},{'zoom':99},{'basemap':'unknown'},{'overlay':{'image':'https://attacker.test/a.svg','bounds':[[1,2],[3,4]]}},{'overlay':{'image':'/assets/plan.png','bounds':[[3,4],[1,2]]}}]:
            with self.subTest(patch=patch),self.assertRaises(ValueError):map_config.outdoor_map(patch)
    def test_building_fences(self):
        maps=[{'name':'전시장','image':'/assets/plan.png','geofence':{'enabled':True,'entrance':[34.75,127.75],'bounds':[[34.74,127.74],[34.76,127.76]]}}]
        clean=map_config.building_maps(maps);self.assertEqual(clean[0]['geofence']['exit_buffer'],40)
        with self.assertRaises(ValueError):map_config.building_maps(maps+maps)
        maps[0]['geofence']['max_accuracy']=10000
        with self.assertRaises(ValueError):map_config.building_maps(maps)
    def test_graph_sanitizes_and_validates_edges(self):
        graph={'nodes':[{'id':'a','name':'입구','lat':34.75,'lng':127.75},{'id':'b','name':'부스','lat':34.751,'lng':127.75}],'edges':[{'from':'a','to':'b','closed':False}]}
        nodes,edges=map_config.graph(graph);self.assertEqual(edges[0]['closed'],False)
        graph['edges'].append({'from':'b','to':'a'})
        with self.assertRaises(ValueError):map_config.graph(graph)
        graph['edges']=[{'from':'a','to':'missing'}]
        with self.assertRaises(ValueError):map_config.graph(graph)
        graph['edges']=[];graph['nodes'][0]['lat']=math.inf
        with self.assertRaises(ValueError):map_config.graph(graph)
