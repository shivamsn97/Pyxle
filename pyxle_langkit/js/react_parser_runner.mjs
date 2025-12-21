import { readFile } from 'node:fs/promises';
import { argv, exit } from 'node:process';
import { parse } from '@babel/parser';

const [, , sourcePath] = argv;

if (!sourcePath) {
  console.error(JSON.stringify({ ok: false, message: 'Expected path to JSX source file.' }));
  exit(1);
}

const parserOptions = {
  sourceType: 'module',
  plugins: [
    'jsx',
    'typescript',
    'classProperties',
    'classPrivateMethods',
    'decorators-legacy',
    'topLevelAwait',
  ],
  errorRecovery: false,
};

const source = await readFile(sourcePath, 'utf8');

function symbolLocation(node) {
  if (!node || !node.loc || !node.loc.start) {
    return { line: null, column: null };
  }
  return { line: node.loc.start.line, column: node.loc.start.column };
}

function resolveIdentifierName(node) {
  if (!node) {
    return null;
  }
  if (node.type === 'Identifier') {
    return node.name;
  }
  if (node.id && node.id.name) {
    return node.id.name;
  }
  return null;
}

function extractVariableSymbols(declaration) {
  if (!declaration || declaration.type !== 'VariableDeclaration') {
    return [];
  }
  const symbols = [];
  for (const declarator of declaration.declarations) {
    if (declarator.id && declarator.id.type === 'Identifier') {
      symbols.push({
        name: declarator.id.name,
        kind: 'named-export',
        ...symbolLocation(declarator.id),
      });
    }
  }
  return symbols;
}

function collectSymbols(ast) {
  const symbols = [];
  const pushSymbol = (name, kind, locSource) => {
    symbols.push({ name, kind, ...symbolLocation(locSource) });
  };

  for (const node of ast.program.body) {
    if (node.type === 'ExportDefaultDeclaration') {
      const name = resolveIdentifierName(node.declaration) ?? 'default';
      pushSymbol(name, 'default-export', node.declaration ?? node);
      continue;
    }

    if (node.type === 'ExportNamedDeclaration') {
      if (node.declaration) {
        const decl = node.declaration;
        if (decl.type === 'FunctionDeclaration' || decl.type === 'ClassDeclaration') {
          const name = resolveIdentifierName(decl) ?? 'anonymous';
          pushSymbol(name, 'named-export', decl);
          continue;
        }
        for (const entry of extractVariableSymbols(decl)) {
          symbols.push(entry);
        }
        continue;
      }

      for (const specifier of node.specifiers ?? []) {
        const exported = specifier.exported?.name ?? null;
        if (exported) {
          pushSymbol(exported, 'named-export', specifier.exported ?? specifier);
        }
      }
    }
  }

  return symbols;
}

try {
  const ast = parse(source, parserOptions);
  const symbols = collectSymbols(ast);
  process.stdout.write(JSON.stringify({ ok: true, symbols }));
} catch (error) {
  const payload = {
    ok: false,
    message: error.message,
    line: error.loc?.line ?? null,
    column: error.loc?.column ?? null,
  };
  process.stdout.write(JSON.stringify(payload));
  exit(1);
}
