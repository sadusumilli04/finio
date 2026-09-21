import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import Accounts from './pages/Accounts'
import Dashboard from './pages/Dashboard'
import Import from './pages/Import'
import Insights from './pages/Insights'
import Recurring from './pages/Recurring'
import Transactions from './pages/Transactions'

const links = [
  ['/', 'Dashboard'],
  ['/insights', 'Insights'],
  ['/transactions', 'Transactions'],
  ['/recurring', 'Recurring'],
  ['/import', 'Import'],
  ['/accounts', 'Accounts'],
] as const

export default function App() {
  return (
    <BrowserRouter>
      <header className="nav">
        <span className="brand">Finio</span>
        {links.map(([to, label]) => (
          <NavLink key={to} to={to} end={to === '/'}>
            {label}
          </NavLink>
        ))}
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/insights" element={<Insights />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/recurring" element={<Recurring />} />
          <Route path="/import" element={<Import />} />
          <Route path="/accounts" element={<Accounts />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
