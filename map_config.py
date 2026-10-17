"""Validation of public map data. All coordinates are WGS84; bounds are SW, NE."""
import math
import re


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('지도 숫자 범위가 올바르지 않습니다.')
    return value


def point(value):
    if not isinstance(value,list) or len(value)!=2: raise ValueError('위도·경도 쌍이 필요합니다.')
    return [number(value[0],-85,85),number(value[1],-180,180)]


def bounds(value):
    if not isinstance(value,list) or len(value)!=2: raise ValueError('남서·북동 경계가 필요합니다.')
    sw,ne=point(value[0]),point(value[1])
    if sw[0]>=ne[0] or sw[1]>=ne[1]: raise ValueError('경계 순서를 확인하세요.')
    return [sw,ne]


def image(value):
    if not isinstance(value,str) or not re.fullmatch(r'/assets/[\w.-]+',value): raise ValueError('등록한 이미지 경로가 필요합니다.')
    return value


def label(value, limit=100):
    if not isinstance(value,str) or not value.strip() or len(value)>limit: raise ValueError('지도 이름을 확인하세요.')
    return value.strip()


def building_maps(value):
    if not isinstance(value,list) or len(value)>30: raise ValueError('건물 지도를 확인하세요.')
    result=[];names=set()
    for item in value:
        if not isinstance(item,dict): raise ValueError('건물 지도 형식을 확인하세요.')
        name=label(item.get('name'))
        if name in names: raise ValueError('건물명이 중복됩니다.')
        names.add(name);entry={'name':name,'image':image(item.get('image'))}
        if item.get('geofence') is not None:
            f=item['geofence']
            if not isinstance(f,dict) or type(f.get('enabled',False)) is not bool: raise ValueError('진입 설정을 확인하세요.')
            entry['geofence']={'enabled':f.get('enabled',False),'entrance':point(f.get('entrance')),'bounds':bounds(f.get('bounds')),'entry_radius':number(f.get('entry_radius',20),5,100),'exit_buffer':number(f.get('exit_buffer',40),10,500),'dwell_ms':number(f.get('dwell_ms',10000),2000,120000),'max_accuracy':number(f.get('max_accuracy',35),5,100)}
        result.append(entry)
    return result


def outdoor_map(value):
    if not isinstance(value,dict): raise ValueError('야외 지도 설정을 확인하세요.')
    provider=value.get('basemap','osm')
    if provider not in ['osm','satellite','none']: raise ValueError('지도 제공자를 확인하세요.')
    result={'center':point(value.get('center',[34.7523,127.7468])),'zoom':number(value.get('zoom',17),2,20),'basemap':provider}
    if value.get('overlay'):
        overlay=value['overlay']
        result['overlay']={'image':image(overlay.get('image')),'bounds':bounds(overlay.get('bounds')),'opacity':number(overlay.get('opacity',.65),0,1),'rotation':number(overlay.get('rotation',0),-180,180)}
    return result


def graph(value):
    if not isinstance(value,dict): raise ValueError('보행로 형식을 확인하세요.')
    nodes=value.get('nodes',[]);edges=value.get('edges',[])
    if not isinstance(nodes,list) or not isinstance(edges,list) or len(nodes)>2000 or len(edges)>6000: raise ValueError('보행로 수를 확인하세요.')
    ids=set();clean_nodes=[]
    for node in nodes:
        if not isinstance(node,dict): raise ValueError('지점 형식을 확인하세요.')
        nid=label(node.get('id'),60)
        if nid in ids: raise ValueError('중복 보행 지점입니다.')
        ids.add(nid)
        coord=point([node.get('lat'),node.get('lng')])
        clean_nodes.append({'id':nid,'name':label(node.get('name'),120),'lat':coord[0],'lng':coord[1]})
    clean_edges=[];pairs=set()
    for edge in edges:
        if not isinstance(edge,dict) or edge.get('from') not in ids or edge.get('to') not in ids or edge['from']==edge['to'] or type(edge.get('closed',False)) is not bool: raise ValueError('보행 연결을 확인하세요.')
        pair=tuple(sorted([edge['from'],edge['to']]))
        if pair in pairs: raise ValueError('중복 보행 연결입니다.')
        pairs.add(pair);clean_edges.append({'from':edge['from'],'to':edge['to'],'closed':edge.get('closed',False)})
    return clean_nodes,clean_edges
