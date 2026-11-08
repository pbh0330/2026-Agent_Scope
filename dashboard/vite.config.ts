import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// /api는 토큰 수집기 사용 현황 API(agentscope-usage-api, 기본 127.0.0.1:8088)로 넘긴다.
// API가 꺼져 있으면 대시보드는 public/data/usage-api의 저장된 응답을 쓴다.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8088' } },
})
