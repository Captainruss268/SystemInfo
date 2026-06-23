import React, { useEffect, useRef, useState, useCallback } from 'react';
import ThemeToggle from './ThemeToggle';
import './SidebarNavigation.css';

const SidebarNavigation: React.FC = () => {
  const [activeSection, setActiveSection] = useState<string>('');
  const scrollLock = useRef(false);
  const ticking = useRef(false);

  const sections = [
    { id: 'system', label: 'System & CPU', selector: '.system-info-card' },
    { id: 'hardware', label: 'Hardware', selector: '.hardware-info-card' },
    { id: 'network', label: 'Network', selector: '.network-info-card' },
    { id: 'performance', label: 'Performance', selector: '.performance-chart-container' },
  ];

  const updateActiveSection = useCallback(() => {
    if (scrollLock.current) return;
    let closestId = sections[0].id;
    let closestDist = Infinity;
    for (const section of sections) {
      const el = document.querySelector(section.selector);
      if (el) {
        const rect = el.getBoundingClientRect();
        const dist = Math.abs(rect.top);
        if (dist < closestDist) {
          closestDist = dist;
          closestId = section.id;
        }
      }
    }
    setActiveSection(closestId);
  }, []);

  useEffect(() => {
    updateActiveSection();
    const handleScroll = () => {
      if (!ticking.current) {
        window.requestAnimationFrame(() => {
          updateActiveSection();
          ticking.current = false;
        });
        ticking.current = true;
      }
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [updateActiveSection]);

  const scrollToSection = (selector: string, id: string) => {
    scrollLock.current = true;
    setActiveSection(id);
    const element = document.querySelector(selector);
    if (element) element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setTimeout(() => { scrollLock.current = false; }, 600);
  };

  return (
    <>
      <nav className="sidebar-navigation">
        <div className="sidebar-header">
          <div className="theme-toggle-left"><ThemeToggle /></div>
        </div>
        <div className="sidebar-content">
          {sections.map(section => (
            <button
              key={section.id}
              className={`nav-link ${activeSection === section.id ? 'active' : ''}`}
              onClick={() => scrollToSection(section.selector, section.id)}
            >
              {section.label}
            </button>
          ))}
        </div>
      </nav>
    </>
  );
};

export default SidebarNavigation;