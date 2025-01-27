import React from 'react';
import './ButtonWithStatus.css';

const ButtonWithStatus = ({ 
  onClick, 
  disabled, 
  isLoading, 
  loadingText, 
  children, 
  className = '',
  title
}) => {
  const buttonClass = `button-with-status ${className} ${isLoading ? 'loading' : ''}`;
  
  return (
    <button 
      onClick={onClick}
      disabled={disabled || isLoading}
      className={buttonClass}
      title={title}
    >
      {isLoading ? (loadingText || 'Processing...') : children}
    </button>
  );
};

export default ButtonWithStatus;
