import React from 'react';
import './TechStack.css';

const techStack = [
  {
    name: 'React',
    logo: (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="-11.5 -10.23174 23 20.46348" width="50" height="50">
        <title>React Logo</title>
        <circle cx="0" cy="0" r="2.05" fill="#61dafb" />
        <g stroke="#61dafb" strokeWidth="1" fill="none">
          <ellipse rx="11" ry="4.2" />
          <ellipse rx="11" ry="4.2" transform="rotate(60)" />
          <ellipse rx="11" ry="4.2" transform="rotate(120)" />
        </g>
      </svg>
    ),
  },
  {
    name: 'Python',
    logo: (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="50" height="50" fill="#3776AB">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93s3.05-7.44 7-7.93v15.86zm2 0V4.07c3.95.49 7 3.85 7 7.93s-3.05 7.44-7 7.93z" />
      </svg>
    ),
  },
  {
    name: 'Node.js',
    logo: (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="50" height="50" fill="#339933">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1.04 15.64l-3.3-5.72h6.6l-3.3 5.72zm-4.3-7.28l1.9-3.29h4.88l1.9 3.29-4.34 7.52-4.34-7.52z" />
      </svg>
    ),
  },
  {
    name: 'Flask',
    logo: (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="50" height="50" fill="#000000">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-12h2v8h-2v-8z" />
      </svg>
    ),
  },
  {
    name: 'Docker',
    logo: (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="50" height="50" fill="#2496ED">
        <path d="M21.99 6.88c-.1-.4-.4-.74-.8-.93l-8-4.44c-.4-.22-.9-.22-1.3 0l-8 4.44c-.4.2-.7.53-.8.93L2 12l1.11 5.12c.1.4.4.74.8.93l8 4.44c.4.22.9.22 1.3 0l8-4.44c.4-.2.7-.53.8-.93L22 12l-1.01-5.12zM12 3.6l6.6 3.67-1.4 6.45H6.8L5.4 7.27 12 3.6zm-1 15.8V13h2v6.4l-1 .55-1-.55z" />
      </svg>
    ),
  },
];

const TechStack = () => {
  return (
    <div className="tech-stack-container">
      <h2>Powered By</h2>
      <div className="tech-grid">
        {techStack.map((tech) => (
          <div key={tech.name} className="tech-item">
            {tech.logo}
            <span>{tech.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default TechStack;
