import React, { useEffect, useState } from 'react';
import ThemeToggle from './ThemeToggle';
import './SidebarNavigation.css';

const SidebarNavigation: React.FC = () => {
  const [activeSection, setActiveSection] = useState<string>('');

  const sections = [
    { id: 'network', label: 'Network', selector: '.network-info-card' },
    { id: 'system', label: 'System & CPU', selector: '.system-info-card' },
    { id: 'hardware', label: 'Hardware', selector: '.hardware-info-card' },
    { id: 'performance', label: 'Performance', selector: '.performance-chart-container' },
  ];

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        let maxRatio = 0, mostVisibleSectionId = '';
        for (const entry of entries) {
          if (entry.intersectionRatio > maxRatio) {
            const element = entry.target;
            const sectionId = sections.find(section => element.matches(section.selector))?.id;
            if (sectionId) {
              maxRatio = entry.intersectionRatio;
              mostVisibleSectionId = sectionId;
            }
          }
        }
        setActiveSection(maxRatio === 0 ? '' : mostVisibleSectionId);
      },
      { threshold: [0.1, 0.2, 0.3, 0.4, 0.5], rootMargin: '-10% 0px -40% 0px' }
    );

    sections.forEach(section => {
      const element = document.querySelector(section.selector);
      if (element) observer.observe(element);
    });

    return () => observer.disconnect();
  }, []);

  const scrollToSection = (selector: string) => {
    const element = document.querySelector(selector);
    if (element) element.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <>
      <nav className="sidebar-navigation">
        <div className="theme-toggle-left"><ThemeToggle /></div>
        <div className="sidebar-content">
          {sections.map(section => (
            <button
              key={section.id}
              className={`nav-link ${activeSection === section.id ? 'active' : ''}`}
              onClick={() => scrollToSection(section.selector)}
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
