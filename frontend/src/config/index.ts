export const config = {
  mockApi: import.meta.env.VITE_MOCK_API === 'true',
  apiUrl: import.meta.env.VITE_API_URL ?? '/api/v1',
} as const
