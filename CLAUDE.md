# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
尽量使用中文回复

## Project Overview

This is a personal blog built with **Hugo**, a fast static site generator. The site is deployed to GitHub Pages via automated CI/CD. The blog uses the **Paper theme** as the primary theme.

## Key Commands

### Local Development
- **Preview site locally**: `hugo server -D`
  - Runs a development server at `http://localhost:1313`
  - The `-D` flag includes draft posts

### Building
- **Build for production**: `hugo --gc --minify`
  - Generates the static site in the `public/` directory
  - `--gc` performs garbage collection, removing unused cache files
  - `--minify` minifies CSS and HTML output

### Content Management
- **Create a new post**: `hugo new posts/post-name.md`
  - Uses the archetype template from `archetypes/default.md`
  - Posts are created in the `content/posts/` directory
  - Set `draft: false` in front matter to publish

## Project Structure

```
/
├── content/             # Blog content (Markdown files)
│   └── posts/          # Individual blog posts
├── public/             # Generated static site (DO NOT edit directly)
├── themes/             # Hugo themes (Git submodules)
│   ├── paper/          # Primary theme (active)
│   └── ananke/         # Alternative theme
├── layouts/            # Custom layout overrides (currently empty)
├── assets/             # Static assets (currently empty)
├── archetypes/         # Content templates
└── hugo.toml           # Hugo configuration
```

## Configuration

**hugo.toml** contains the main configuration:
- **baseURL**: `https://ddnio.github.io/` - GitHub Pages URL
- **theme**: `paper` - Uses the Paper theme
- **params**: Profile information (avatar, name, bio, GitHub link)

## Theme & Customization

The site uses the **Paper theme** (via Git submodule). Key points:
- Do not edit theme files directly; use the `layouts/` directory for overrides
- Currently, no custom layout overrides are in place
- Theme is pulled from: https://github.com/nanxiaobei/hugo-paper

## Deployment

Automated deployment is configured via GitHub Actions:
- **Trigger**: Pushes to `main` branch or manual workflow dispatch
- **Environment**: Hugo 0.127.0 with Dart Sass support
- **Process**:
  1. Checks out code (including Git submodules)
  2. Installs Hugo and dependencies
  3. Builds the site with production settings
  4. Deploys the `public/` directory to GitHub Pages
- **Workflow file**: `.github/workflows/hugo.yaml`

## Front Matter

Posts should include standard Hugo front matter. Example:
```yaml
---
title: "Post Title"
date: 2024-06-25T00:00:00Z
draft: false
---
```

## Notes for Contributors

- The `public/` directory is generated during build and should not be committed with manual edits
- When creating new posts, ensure `draft: false` before pushing to `main` to publish
- Changes to `content/` or `hugo.toml` will trigger automatic deployment
- The repository includes two themes as submodules, but only the `paper` theme is active
