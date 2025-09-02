# AI Search Multimodal - Frontend

A modern, production-ready React frontend application for AI-powered multimodal search capabilities.

## 🏗️ Architecture Overview

This frontend is built with modern React patterns and TypeScript, featuring:

- **Component-based architecture** with clear separation of concerns
- **Type-safe development** with comprehensive TypeScript configuration
- **Context-based state management** for theme and application state
- **Error boundaries** for graceful error handling
- **Performance optimizations** with code splitting and lazy loading
- **Production-ready build pipeline** with Vite

## 📁 Project Structure

```
src/
├── api/                    # API layer and data fetching
│   ├── api.ts             # Legacy API (preserved for compatibility)
│   ├── enhanced-api.ts    # Enhanced API with better error handling
│   ├── defaults.ts        # Default configurations
│   └── models.ts          # Legacy models (preserved for compatibility)
├── components/            # React components organized by feature
│   ├── admin/            # Admin panel components
│   ├── chat/             # Chat interface components
│   ├── layout/           # Layout and navigation components
│   ├── search/           # Search functionality components
│   ├── shared/           # Reusable shared components
│   │   ├── ErrorBoundary/
│   │   └── Loading/
│   └── upload/           # File upload components
├── constants/            # Application constants and configuration
│   ├── app.ts           # App-wide constants
│   └── index.ts         # Barrel exports
├── contexts/            # React Context providers
│   ├── ThemeContext.tsx # Theme management
│   └── index.ts         # Barrel exports
├── hooks/              # Custom React hooks
│   ├── useChat.tsx     # Chat functionality
│   ├── useConfig.tsx   # Configuration management
│   └── useTheme.tsx    # Legacy theme hook (preserved)
├── pages/              # Page-level components
│   ├── App.tsx         # Main application component
│   └── App.css         # Application styles
├── types/              # TypeScript type definitions
│   ├── api.ts          # API-related types
│   ├── chat.ts         # Chat and messaging types
│   ├── common.ts       # Common utility types
│   ├── config.ts       # Configuration types
│   └── index.ts        # Barrel exports
├── utils/              # Utility functions
│   ├── errors.ts       # Error handling utilities
│   ├── helpers.ts      # General helper functions
│   ├── validation.ts   # Validation utilities
│   └── index.ts        # Barrel exports
└── main.tsx           # Application entry point
```

## 🚀 Getting Started

### Prerequisites

- Node.js >= 18.0.0
- npm >= 8.0.0

### Installation

```bash
npm install
```

### Development

```bash
# Start development server
npm run dev

# Type checking
npm run type-check

# Linting
npm run lint
npm run lint:fix

# Formatting
npm run format
npm run format:check
```

### Building

```bash
# Production build
npm run build

# Development build (with source maps)
npm run build:dev

# Bundle analysis
npm run build:analyze
```

## 🛠️ Development Features

### Type Safety

- Comprehensive TypeScript configuration with strict mode
- Path aliases for clean imports (`@/components`, `@/types`, etc.)
- Strong typing for all API interactions and component props

### Code Quality

- ESLint with strict rules for TypeScript and React
- Prettier for consistent code formatting
- Import sorting and organization
- Automated code quality checks

### Error Handling

- Global error boundaries for graceful error recovery
- Type-safe error handling with custom error classes
- Comprehensive logging and debugging support

### Performance

- Code splitting with dynamic imports
- Optimized bundle sizes with manual chunks
- Tree shaking for unused code elimination
- Development and production optimizations

### Developer Experience

- Hot module replacement for fast development
- Path aliases for clean imports
- Comprehensive linting and formatting
- Type checking and error reporting

## 📦 Key Dependencies

### Core Libraries

- **React 18.3** - Modern React with concurrent features
- **TypeScript 5.6** - Type safety and modern JavaScript features
- **Vite 6.0** - Fast build tool and development server

### UI Framework

- **Fluent UI React Components 9.56** - Microsoft's design system
- **Fluent UI React Icons 2.0** - Comprehensive icon library

### Development Tools

- **ESLint 9.13** - Code linting and quality enforcement
- **Prettier 3.4** - Code formatting
- **TypeScript ESLint 8.11** - TypeScript-specific linting rules

## 🎨 Theming

The application supports both light and dark themes with:

- System preference detection
- Manual theme switching
- Persistent theme preferences
- Fluent UI theme integration

## 🔧 Configuration

### Environment Variables

The application uses Vite's environment variable system:

- `import.meta.env.DEV` - Development mode detection
- `import.meta.env.PROD` - Production mode detection

### API Configuration

API endpoints are configured in `src/constants/app.ts` and can be customized for different environments.

## 🧪 Testing

Currently, the project structure supports testing but tests are not yet implemented. The architecture is ready for:

- Unit tests with Jest or Vitest
- Component testing with React Testing Library
- E2E testing with Playwright or Cypress

## 🚀 Deployment

The application builds to `../backend/static` for integration with the Python backend. The build process:

1. Type checks all TypeScript files
2. Builds optimized bundles with Vite
3. Generates source maps for debugging
4. Optimizes assets and implements code splitting

## 🔄 Migration Notes

This refactored version maintains full backward compatibility while adding:

- Enhanced type safety
- Better error handling
- Improved developer experience
- Production-ready architecture
- Performance optimizations

All existing functionality has been preserved and enhanced.

## 📈 Performance Considerations

- Bundle splitting reduces initial load time
- Tree shaking eliminates unused code
- Optimized imports with barrel exports
- Efficient re-rendering with proper React patterns
- Memory leak prevention with proper cleanup

## 🔗 Integration

The frontend integrates with the Python backend through:

- RESTful API endpoints
- Server-sent events for real-time updates
- File upload capabilities
- Proxy configuration for development
