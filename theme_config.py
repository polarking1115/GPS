"""Validated, public key-visual display preferences. Never accepts CSS or HTML."""
import re


def defaults():
    return {'layout': 'split', 'show_title': True, 'show_slogan': True,
            'title_size': 32, 'align': 'left', 'text_color': '#102b55',
            'surface_color': '#fffcf5', 'overlay_tone': 'none',
            'overlay_opacity': 35, 'position_x': 50, 'position_y': 50,
            'zoom': 100, 'fit': 'contain', 'poster': ''}


def validate(value, previous=None):
    result = defaults()
    if isinstance(previous, dict):
        result.update({k: v for k, v in previous.items() if k in result})
    if not isinstance(value, dict) or any(k not in result for k in value):
        raise ValueError('키비주얼 설정 항목을 확인하세요.')
    enums = {'layout': ['split', 'background', 'poster'],
             'align': ['left', 'center', 'right'],
             'overlay_tone': ['none', 'light', 'dark'], 'fit': ['contain', 'cover']}
    bounds = {'title_size': (20, 48), 'overlay_opacity': (0, 80),
              'position_x': (0, 100), 'position_y': (0, 100), 'zoom': (100, 200)}
    for key, item in value.items():
        if key in enums:
            if not isinstance(item, str) or item not in enums[key]:
                raise ValueError('키비주얼 표시 방식과 선택값을 확인하세요.')
        elif key in bounds:
            low, high = bounds[key]
            if type(item) is not int or not low <= item <= high:
                raise ValueError('키비주얼 크기·위치·필터 범위를 확인하세요.')
        elif key in ['show_title', 'show_slogan']:
            if type(item) is not bool:
                raise ValueError('제목·슬로건 표시 여부를 확인하세요.')
        elif key in ['text_color', 'surface_color']:
            if not isinstance(item, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', item):
                raise ValueError('키비주얼 색상은 6자리 색상 코드로 입력하세요.')
            item = item.lower()
        elif key == 'poster':
            if not isinstance(item, str) or (item and not re.fullmatch(r'/assets/[\w-][\w.-]*\.(?:png|jpe?g|webp)', item, re.I)):
                raise ValueError('원본 포스터는 등록한 PNG·JPEG·WebP 이미지 경로를 사용하세요.')
        result[key] = item
    return result
