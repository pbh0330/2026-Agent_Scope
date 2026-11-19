import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// /api는 토큰 수집기 사용 현황 API(agentscope-usage-api)로 넘긴다. API는 CORS 헤더를 보내지 않으므로 반드시 프록시를 거친다.
// 주소는 USAGE_API_TARGET으로 바꾼다(기본: 같은 PC의 127.0.0.1:8088).
//   테스트베드 시연: USAGE_API_TARGET=http://<TB_GW_IP>:8088  (셸 환경변수 또는 dashboard/.env.local)
// API가 꺼져 있으면 대시보드는 public/data/usage-api의 저장된 응답을 쓴다.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const target = env.USAGE_API_TARGET || 'http://127.0.0.1:8088'
  return {
    plugins: [react()],
    server: { proxy: { '/api': { target, changeOrigin: true } } },
    preview: { proxy: { '/api': { target, changeOrigin: true } } },
  }
})
