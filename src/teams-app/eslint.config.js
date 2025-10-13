import eslintPluginReact from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import tseslint from '@typescript-eslint/eslint-plugin';
import tsParser from '@typescript-eslint/parser';
import eslintPluginImport from 'eslint-plugin-import';
import prettier from 'eslint-config-prettier';

/** @type {import('eslint').Linter.Config[]} */
const config = [
  {
    files: ['src/**/*.ts', 'scripts/**/*.ts'],
    ignores: ['src/tab/web/src/**/*'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        project: './tsconfig.json',
        sourceType: 'module'
      }
    },
    plugins: {
      '@typescript-eslint': tseslint,
      import: eslintPluginImport
    },
    rules: {
      ...tseslint.configs['recommended-type-checked'].rules,
      ...tseslint.configs['stylistic-type-checked'].rules,
      'import/order': [
        'warn',
        {
          groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
          'newlines-between': 'always'
        }
      ],
      '@typescript-eslint/no-floating-promises': ['error', { ignoreVoid: true }],
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }
      ],
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }]
    }
  },
  {
    files: ['src/tab/web/src/**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        project: './tsconfig.client.json',
        ecmaFeatures: {
          jsx: true
        }
      }
    },
    plugins: {
      '@typescript-eslint': tseslint,
      react: eslintPluginReact,
      'react-hooks': reactHooks,
      'jsx-a11y': jsxA11y,
      import: eslintPluginImport
    },
    settings: {
      react: {
        version: 'detect'
      }
    },
    rules: {
      ...tseslint.configs['recommended-type-checked'].rules,
      ...tseslint.configs['stylistic-type-checked'].rules,
      ...eslintPluginReact.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,
      'react/jsx-no-target-blank': 'off',
      'react/react-in-jsx-scope': 'off',
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }
      ],
      '@typescript-eslint/naming-convention': [
        'error',
        {
          selector: 'variableLike',
          format: ['camelCase', 'PascalCase', 'UPPER_CASE']
        }
      ]
    }
  },
  {
    files: ['**/*.{ts,tsx,js,jsx}'],
    rules: {
      ...prettier.rules
    }
  }
];

export default config;
