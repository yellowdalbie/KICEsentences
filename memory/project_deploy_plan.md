---
name: 배포 아키텍처 결정사항
description: 배포 버전 구성 방식, 벡터 임베딩 대안, 클러스터 검색 방식 결정
type: project
---

## 배포 방식 결정 (2026-03-17)

### 핵심 원칙
배포 패키지에는 BGE-m3-ko 모델(2.1GB)을 포함하되, 사전 계산 인덱스를 활용해 런타임 연산 최소화.

### 벡터 유사도 사전 계산 인덱스 (미구현, 향후 배포 시 필수)
- **방식**: 개발 PC에서 전체 스텝 간 코사인 유사도 계산 → 각 스텝당 상위 50개만 저장
- **파일**: `step_similarity_index.json` (~1.5MB)
- **효과**: 런타임에 모델 임베딩 없이 단순 테이블 조회
- **업데이트**: 새 문항 추가 시 Oracle Cloud 또는 개발 PC에서 rebuild → 배포 파일에 포함

**Why:** BGE-m3-ko 2.1GB 모델은 설치 용량이 크지만, 런타임 쿼리 임베딩 속도는 0.05초로 허용 가능. 향후 용량 이슈 대두 시 이 방식으로 전환.

### 트리거 클러스터 검색 (구현 완료)
- **파일**: `trigger_clusters.json`, `step_clusters.json`
- **빌드 스크립트**: `build_trigger_clusters.py --threshold 0.85`
- **임계값**: 0.85 (기본값). 추후 테스트 후 조정 가능
  - 높을수록 잘게 쪼개짐 (0.90), 낮을수록 크게 묶임 (0.80)
  - 현재 결과: 775 클러스터, 77.2% 스텝이 다중 클러스터에 속함
- **알려진 이슈**: 클러스터 552에서 "극한값"(limit)과 "극값"(extreme value) 혼재 → threshold 상향 시 분리될 것

### 검색 가중치 (search_engine.py)
- **클러스터 있을 때**: 클러스터(0.40) + BM25(0.30) + 벡터코사인(0.20) + CPT(0.10)
- **클러스터 없을 때 (폴백)**: BM25(0.45) + 벡터코사인(0.40) + CPT(0.15)

**How to apply:** 업데이트 배포 시 `build_db.py` → `build_vectors.py` → `build_trigger_clusters.py` 순서로 실행 후 세 파일(`kice_database.sqlite`, `kice_step_vectors.npz`, `step_clusters.json`, `trigger_clusters.json`) 배포.
