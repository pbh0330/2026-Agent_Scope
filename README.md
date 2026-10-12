# AgentScope Dashboard Starter

React + TypeScript + Vite 기반의 AgentScope 대시보드 UI 시작 템플릿입니다.

## 현재 구현된 화면
- Overview: 요약 카드, 관계도 미리보기, 최근 위협, 자산 목록
- Asset Graph: 자산 검색/유형 필터, 노드 선택, 상세 정보와 증거 표시
- Threats: S1–S5 시나리오 목록
- Token Usage: 토큰 사용량 차트 형태의 목업 화면

## 실행 방법

Node.js LTS가 설치되어 있는지 확인한 뒤, 이 폴더에서 실행합니다.

```powershell
npm install
npm run dev
```

터미널에 출력되는 로컬 주소(보통 `http://localhost:5173`)를 브라우저에서 엽니다.

빌드 확인:

```powershell
npm run build
```

## 중요
- 현재 수치, 자산, 관계선, 위협 목록은 UI 확인용 **목업 데이터**입니다.
- 관계선은 실제 스캐너 결과를 반영하지 않습니다.
- 정적 분석에서 확인한 선언/노출과 추론된 `MAY_CALL` 관계를 구분해야 합니다.
- 실제 호출 여부를 정적 분석만으로 확정하지 않습니다.
- 비밀값은 화면에 표시하지 않습니다. 자격 증명은 실제 연동 시 유형/참조/범위만 표시하도록 설계합니다.
- 스캐너 JSON 및 Prometheus/Tempo 등의 텔레메트리 연동은 다음 단계에서 구현합니다.

## 주요 파일
- `src/App.tsx`: 페이지 및 UI 구성
- `src/data/mockData.ts`: 샘플 자산과 위협 데이터
- `src/types.ts`: TypeScript 타입
- `src/styles.css`: 전체 스타일
