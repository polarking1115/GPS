# 타사 구성요소 및 지도 출처

## Leaflet 1.9.4

- 프로젝트: https://leafletjs.com/
- 소스 배포: npm 공식 레지스트리의 `leaflet@1.9.4`
- 라이선스: BSD-2-Clause. 전문은 `public/vendor/leaflet/LICENSE`에 보관한다.
- 파일: 로컬 JS/CSS와 기본 아이콘. CDN 스크립트 없이 사용한다.
- npm 배포 tarball의 SHA-512 integrity를 레지스트리 메타데이터와 대조했다.

```
sha512-nxS1ynzJOmOlHp+iL3FyWqK89GtNL8U8rvlMOsQdTTssxZwCXh8N2NB3GDQOL+YR3XnWyZAxwQixURb+FA74PA==
```

## 지도 배경

- 일반 지도: https://tile.openstreetmap.org/{z}/{x}/{y}.png
- 저작권: © OpenStreetMap contributors. 지도에 출처 링크를 표시한다.
- 이용 정책: https://operations.osmfoundation.org/policies/tiles/
- 위성/항공사진: Esri World Imagery, `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`
- 출처 표기: Esri, Maxar, Earthstar Geographics 및 GIS User Community. 표시 위치/확대에 따라 실제 자료 출처가 다를 수 있다.
- 서비스 정보: https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer

키 없이 접근 가능한 공개 타일 연결 후보를 UI에 제공한 것이며, 상업적 운영 권리·가용성·무제한 용량을 보장하지 않는다. 실제 행사 전에 제공자별 최신 이용약관·귀속 표기·트래픽 제한·필요 계정을 확인하고, 규모에 맞는 계약형 타일 서비스로 전환할 수 있다. 배경지도 전체를 오프라인 저장하거나 일괄 다운로드하지 않는다. GPS 좌표를 플랫폼 서버에 전송하지 않지만, 배경을 선택하면 브라우저가 외부 타일 서버에 직접 연결해 IP와 요청 타일 범위가 전달된다.

## 검증 범위

2026-10-17 이 클라우드에서 외부 타일/서비스 메타데이터 요청은 프록시의 403 응답으로 차단됐다. 지도 렌더링·로컬 보행로·오버레이·GPS 전환 테스트는 대체 타일과 모의 GPS를 사용한다. 실제 타일 수신 성공·현장 위치 정확도는 미검증이다. 실패 시 사용자에게 알리고 배치도·등록 통로는 유지한다.
