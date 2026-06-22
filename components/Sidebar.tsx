'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Sidebar() {
  const pathname = usePathname();

  const navItems = [
    {
      label: 'Menu',
      items: [
        { href: '/', icon: '🏠', text: 'Dashboard' },
        { href: '/settings', icon: '⚙️', text: 'Configuration' },
      ],
    },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">N</div>
          <div className="sidebar-logo-text">
            <span>Nabi</span> AI
          </div>
        </div>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((section) => (
          <div key={section.label}>
            <div className="sidebar-section-label">{section.label}</div>
            {section.items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`sidebar-link ${pathname === item.href ? 'active' : ''}`}
              >
                <span className="sidebar-link-icon">{item.icon}</span>
                {item.text}
              </Link>
            ))}
          </div>
        ))}

        <div>
          <div className="sidebar-section-label">Projets récents</div>
          <div style={{ padding: 'var(--space-3)', color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)' }}>
            Aucun projet pour le moment
          </div>
        </div>
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-version">Nabi AI v0.1.0 — Local</div>
      </div>
    </aside>
  );
}
