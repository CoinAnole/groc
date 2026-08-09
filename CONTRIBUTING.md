# Contributing

Groc is intentionally small. Keep changes boring, explicit, and easy to audit.

## Local Setup

```bash
git clone https://github.com/CoinAnole/groc.git
cd groc
make verify
```

## Engineering Principles

- Keep the shell scripts as shims. Product logic belongs in the Python package.
- Keep auth, transport, wire conversion, and CLI orchestration separated.
- Prefer stdlib code unless a dependency removes real complexity.
- Never print tokens, refresh tokens, or full account identifiers.
- Treat endpoint overrides as dangerous.
- Add focused tests for every behavior change.
- Keep release archives reproducible from tracked files.

### Type checking

Run the type checker locally (not part of `make verify` today):

```bash
ty check .
```

Use ty 0.0.65+ if possible; project pins `tool.ty.environment.python-version` to `"3.11"`.

## Pull Request Checklist

Before opening a PR:

```bash
make verify
scripts/package-release.sh pr-check
```

Include:

- What changed.
- Why it changed.
- How it was verified.
- Any security or compatibility impact.
