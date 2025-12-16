# GitHub Pages Deployment Guide

This guide explains how to deploy DiagTerm Web to GitHub Pages.

## Prerequisites

- GitHub repository with Pages enabled
- Node.js 20+ installed
- npm installed

## Quick Deploy (Automated)

The repository includes a GitHub Actions workflow (`.github/workflows/deploy.yml`) that automatically builds and deploys to GitHub Pages when you push to the `main` branch.

### Setup Steps:

1. **Enable GitHub Pages:**
   - Go to your repository Settings → Pages
   - Under "Source", select "GitHub Actions"
   - Save the settings

2. **Push to main branch:**
   ```bash
   git push origin main
   ```

3. **Monitor deployment:**
   - Go to the "Actions" tab in your repository
   - Watch the "Deploy to GitHub Pages" workflow run
   - Once complete, your site will be available at: `https://exios66.github.io/COMMAND_UI/`

## Manual Deployment

If you prefer to deploy manually:

### 1. Build the application:

```bash
cd web
npm install
VITE_BASE_PATH=/COMMAND_UI/ npm run build
```

### 2. Deploy to GitHub Pages:

**Option A: Using gh-pages branch:**
```bash
npm install -g gh-pages
cd web
gh-pages -d dist
```

**Option B: Using GitHub CLI:**
```bash
gh repo clone Exios66/COMMAND_UI
cd COMMAND_UI/web
npm install
VITE_BASE_PATH=/COMMAND_UI/ npm run build
gh repo deploy COMMAND_UI --dir=dist --branch=gh-pages
```

**Option C: Manual push to gh-pages:**
```bash
cd web
npm install
VITE_BASE_PATH=/COMMAND_UI/ npm run build
cd dist
git init
git add -A
git commit -m "Deploy to GitHub Pages"
git branch -M gh-pages
git remote add origin https://github.com/Exios66/COMMAND_UI.git
git push -f origin gh-pages
```

## Configuration

### Base Path

The application is configured to work with GitHub Pages subdirectory deployment. The base path is set via environment variable:

- **Local development:** Leave empty or use `/`
- **GitHub Pages:** Use `/COMMAND_UI/` (or your repository name)

To change the base path, set the `VITE_BASE_PATH` environment variable before building:

```bash
export VITE_BASE_PATH=/COMMAND_UI/
npm run build
```

### Custom Domain

If you're using a custom domain:

1. Update `vite.config.ts` to use `/` as the base path
2. Update all URLs in `index.html` to use your custom domain
3. Add a `CNAME` file in `web/public/` with your domain name

## Assets

The following assets are referenced in `index.html` and should be added to `web/public/`:

- `favicon.svg` - SVG favicon (recommended)
- `favicon-32x32.png` - 32x32 PNG favicon
- `favicon-16x16.png` - 16x16 PNG favicon
- `apple-touch-icon.png` - 180x180 PNG for iOS
- `favicon-192x192.png` - 192x192 PNG for PWA
- `favicon-512x512.png` - 512x512 PNG for PWA
- `mstile-150x150.png` - 150x150 PNG for Windows tiles
- `og-image.png` - 1200x630 PNG for social sharing

You can generate these using tools like:
- [Favicon Generator](https://realfavicongenerator.net/)
- [Favicon.io](https://favicon.io/)

## Troubleshooting

### 404 Errors on Routes

If you're getting 404 errors, ensure:
1. The base path is correctly set in `vite.config.ts`
2. GitHub Pages is configured to use the correct branch/folder
3. The build output is in the correct directory

### Assets Not Loading

If assets aren't loading:
1. Check that paths in `index.html` start with `/` (absolute paths)
2. Verify the base path matches your GitHub Pages URL structure
3. Check browser console for 404 errors

### Build Failures

If the build fails:
1. Ensure Node.js version is 20+
2. Clear `node_modules` and reinstall: `rm -rf node_modules package-lock.json && npm install`
3. Check for TypeScript errors: `npm run build` should show detailed errors

## Performance Optimization

The build is optimized for production with:
- Code minification (Terser)
- Console.log removal
- Vendor chunk splitting
- Asset optimization

To verify the build:
```bash
cd web
npm run build
npm run preview
```

## Security

The HTML includes security headers:
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- X-XSS-Protection: 1; mode=block
- Referrer-Policy: strict-origin-when-cross-origin

These help protect against common web vulnerabilities.

## Support

For issues or questions:
- Check the main repository README
- Open an issue on GitHub
- Review GitHub Actions logs for deployment errors
