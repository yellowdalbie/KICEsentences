지금까지 논의된 **"수학적 논리 구조화 기반의 해설 생성 엔진(Mathematical Logic-based Explanation Engine) 구축 전략"**을 문서로 정리하였습니다. 이 문서는 향후 프로젝트의 설계도이자, 연구 및 개발의 핵심 가이드라인으로 활용될 것입니다.

---

# [전략 문서] 수학적 논리 구조화 기반의 해설 생성 엔진 구축 전략

**버전:** 1.0  
**상태:** Draft (Planning Phase)  
**핵심 목표:** 단순한 텍스트 생성을 넘어, 성취기준과 수학적 논리 패턴을 기반으로 문항의 차별점(Delta)을 정확히 식별하고 이를 구조화된 데이터(Step Title, Standard)로 출력하는 엔진 구축.

---

## 1. 문제 정의 (Problem Statement)
현재의 해설 작성 방식은 단순한 '작업의 나열'에 그칠 위험이 있으며, 이는 벡터 임베딩 공간의 의미적 응집도를 떨어뜨리고 검색의 정밀도를 저해함. 
핵est 핵심은 **"어떤 성취기준(Ontology)이, 어떤 논리적 변화(State Transition)를 통해 해결되는가"**를 데이터화하는 것이며, 이를 위해 **'성취기준-논리 패턴-차별점'**으로 이어지는 정교한 구조적 설계가 필요함.

## 2. 핵심 설계 원칙 (Core Design Principles)

### 2.1. 성취기준 중심의 논리적 앵커링 (Ontological Anchoring)
*   **성취기준(Standard)**은 해설의 **'근거(Ground)'**이며, 검색의 최상위 필터임.
*   **Step Title**은 성취기준을 구체화한 **'논리적 정점(Semantic Peak)'**이며, [수단 $\to$ 목적]의 구조를 가져야 함.
*   나머지 요소(Trigger, Action, Result)는 Title과 Standard의 정당성을 입증하는 **'증거(Evidence)'** 역할을 수행함.

### 2.2. 차별점 기반의 생성 (Delta-based Generation)
*   새로운 문항의 해설은 기존 DB에 존재하는 **'표준 로직(Standard Pattern)'**과 **'차별적 요소(Delta)'**의 결합임.
*   기존 패턴과 동일한 문제는 단순 재현(Replication)하고, 변형된 문제는 차별점(새로운 조건, 새로운 함수, 새로운 연산)을 Title에 명시적으로 서술함.

---

## 3. 연구 및 개발 로드맵 (Research & Development Roadmap)

### 1단계: 성취기준 판정 로직의 정교화 (Standard Verifier)
*   **목표:** 문항의 수학적 요소(Entity)와 관계(Relation)를 추출하여 성취기준과의 논리적 부합성을 판정.
*   **핵점 과제:** 
    *   문항 내 수학적 개체(수식, 도형, 조건) 추출 알고리즘 개발.
    *   추출된 데이터와 성취기준 정의 간의 '논리적 포함 관계(Subsumption)' 판정 로직 설계.

### 2단계: 해결 로직의 계층적 분류 체계 구축 (Logic Hierarchy)
*   **목표:** 성취기준별로 나타나는 수학적 해결 경로를 유형별로 데이터화.
*   **핵심 과제:**
    *   **Class A (Identical):** 기존 패턴과 95% 이상 일치하는 단순 변형 문제.
    *   **Class B (Variation):** 기존 패턴에 새로운 조건이 추가된 변형 문제.
    *   **Class C (New/Complex):** 새로운 수학적 개념이나 복합적 사고가 필요한 문제.
    *   각 클래스별 '패턴 템플릿' 구축.

### Ⅲ단계: 차별화된 패턴 생성 엔진 구축 (Generation Engine)
*   **목표:** 문항의 특성을 분석하여 최적의 '패턴 템플릿'을 선택하고, 차별화된 문장을 생성.
*   **핵심 기능:**
    *   **Pattern Matching:** 문항의 수학적 구조를 분석하여 적합한 클래스(A/B/C) 결정.
    *   **Delta Extraction:** 기존 패턴과 비교하여 해당 문항만의 '고유한 차이점(Delta)'을 식별.
    *   **Synthesized Title Generation:** `[기존 패턴 템플릿] + [식별된 Delta]` 구조를 결합하여 최종 Step Title 생성.

---

## 4. 기대 효과 (Expected Outcomes)

1.  **데이터 품질의 상향 평준화:** 모든 해설이 일관된 논리 구조와 문체(Syntactic consistency)를 유지함.
2.  **검색 및 활용성 극대화:** 성취기준별, 난이도별, 유형별 정밀한 데이터 쿼리 및 학습 데이터 생성 가능.
3.  **지식 베이스의 확장성:** 새로운 수학적 개념이 도입되어도 '패턴 템플릿' 추가만으로 엔진 업데이트 가능.

---
**Status:** *Draft for Review*
**Next Step:** *Implementation of Phase 1 (Standardization of Pattern Templates)*