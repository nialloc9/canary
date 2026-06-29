import { Routes, Route } from 'react-router-dom'

// Pages — add real implementations here as you build
const Home = () => (
  <div style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
    <h1>Canary</h1>
    <p>Frontend template. Replace this with your application.</p>
  </div>
)

const NotFound = () => (
  <div style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
    <h1>404</h1>
    <p>Page not found.</p>
  </div>
)

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
