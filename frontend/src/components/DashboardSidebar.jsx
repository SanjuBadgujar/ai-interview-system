const navItems = [
  ["⌂", "Home"],
  ["▣", "Interviews"],
  ["⌁", "Analytics"],
  ["♧", "Practice"],
  ["⚙", "Settings"],
];

export default function DashboardSidebar({ compact = false }) {
  return (
    <aside className={`dashboard-sidebar ${compact ? "compact" : ""}`} aria-label="Main navigation">
      <div className="brand">
        <div className="brand-bot">🤖</div>
        {!compact && <div><strong>AI Interview</strong><span>Smart. Real. Personal.</span></div>}
      </div>
      <nav className="side-nav">
        {navItems.map(([icon, label], index) => (
          <button className={`side-nav-item ${index === 0 ? "active" : ""}`} key={label} type="button" title={compact ? label : undefined} aria-label={label}>
            <span>{icon}</span>{!compact && label}
          </button>
        ))}
      </nav>
      {!compact && <div className="sidebar-bottom">
        <div className="theme-switch"><span>◔</span><b>Dark</b><span>☼</span></div>
        <div className="profile-mini"><div className="profile-avatar">C</div><div><b>Interview candidate</b><span>Active session</span></div></div>
      </div>}
    </aside>
  );
}