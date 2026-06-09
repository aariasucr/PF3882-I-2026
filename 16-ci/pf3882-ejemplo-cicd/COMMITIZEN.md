# Commitizen - Guía de Uso Local

Commitizen es una herramienta para crear commits siguiendo el estándar de Conventional Commits y generar automáticamente changelogs y releases.

## Instalación

```bash
pip install commitizen
```

## Configuración (pyproject.toml)

Ya está configurado en `pyproject.toml`. Incluye:
- Tipo de commits permitidos: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`
- Generación automática de CHANGELOG.md
- Versionado semántico

## Uso Local

### 1. Hacer un commit con wizard interactivo

```bash
cz commit
```

Pasos:
1. Selecciona tipo de cambio (feat, fix, docs, etc.)
2. Ingresa scope (opcional, ej: `api`, `database`)
3. Escribe descripción corta
4. Escribe descripción detallada (opcional)
5. Confirma breaking changes (si aplica)

### 2. Generar changelog y bumpar versión

Cuando estés listo para una release:

```bash
cz bump --changelog
```

Esto:
- Lee commits desde último tag
- Incrementa versión (major.minor.patch)
- Genera/actualiza CHANGELOG.md
- Crea nuevo commit de versión
- Crea nuevo git tag

### 3. Ver versión actual

```bash
cz version
```

### 4. Verificar commits

```bash
cz check --from-rev <hash>
```

Valida que los commits sigan el formato.

### 5. Hacer prueba sin aplicar cambios

```bash
cz bump --dry-run --changelog
```

## Tipos de Commits Permitidos

| Tipo | Significado | Semver |
|------|-------------|--------|
| `feat` | Nueva funcionalidad | minor |
| `fix` | Bug fix | patch |
| `docs` | Documentación | patch |
| `style` | Formato de código | patch |
| `refactor` | Refactorización | patch |
| `perf` | Optimización | patch |
| `test` | Tests | patch |
| `chore` | Tareas mantenimiento | - |
| `ci` | CI/CD | - |
| `build` | Build system | - |

## Ejemplos de Commits

```bash
# Nueva feature en módulo API
cz commit
→ Select: feat
→ Scope: api
→ Message: Add GraphQL endpoint for tasks

# Bug fix en database
cz commit
→ Select: fix
→ Scope: database
→ Message: Fix connection pool leak

# Actualizar docs
cz commit
→ Select: docs
→ Scope: (dejar vacío)
→ Message: Update README with Docker setup
```

## Integrar Commitizen con Git Hooks

### Opción 1: prepare-commit-msg hook

Crear `.git/hooks/prepare-commit-msg`:

```bash
#!/bin/bash
exec < /dev/tty
cz commit --hook || true
```

Hacer ejecutable:
```bash
chmod +x .git/hooks/prepare-commit-msg
```

Uso: `git commit` → abre commitizen wizard

### Opción 2: Alias de git

Agregar a `.gitconfig`:

```bash
git config --local alias.c '!cz commit'
```

Uso: `git c` → abre commitizen wizard

### Opción 3: Pre-commit hook (validar commits)

Crear `.git/hooks/commit-msg`:

```bash
#!/bin/bash
cz check --commit-msg-file "$1" || exit 1
```

Hacer ejecutable:
```bash
chmod +x .git/hooks/commit-msg
```

Valida el mensaje ANTES de crear el commit.

## Workflow Completo Recomendado

### Desarrollo diario

```bash
# 1. Hacer cambios
git add app/
git add tests/

# 2. Crear commit con wizard
cz commit

# 3. Verificar que el commit se creó bien
git log --oneline -1
```

### Antes de hacer release

```bash
# 1. Asegurar que todo está en main
git status

# 2. Bumpar versión y generar changelog
cz bump --changelog

# 3. Revisar CHANGELOG.md y commit de bump
git log --oneline -3

# 4. Hacer push con tags
git push origin main --tags
```

## Ver CHANGELOG.md

Después de `cz bump`, revisa:

```bash
cat CHANGELOG.md
```

Muestra:
- Versión
- Fecha
- Features nuevas
- Bug fixes
- Breaking changes

## Troubleshooting

### "No commits found"
Verifica que existan commits con formato válido desde el último tag:
```bash
cz check --from-rev <hash>
```

### Cambiar última versión

Si necesitas ajustar la versión antes de bumpar:
```bash
cz version --set-version 1.2.3
```

### Regenerar changelog

```bash
cz bump --changelog --bump-pre-release
```

## Integración con GitHub Actions

Ya está configurado en `.github/workflows/incrementar_version.yaml`:
- Se ejecuta automáticamente en push a main
- Genera bump, changelog y push a GitHub
- Sube imagen a Docker Hub con etiqueta de versión

No necesitas hacer nada localmente para esto — los commits convencionales en main triggers el workflow automáticamente.
