# DiagTerm

Terminal UI for live system diagnostics + command runner.

## Features

- **Live System Monitoring**: Real-time CPU, memory, disk, and network statistics
- **Process Management**: View top processes by CPU and memory usage
- **Service Monitoring**: Monitor systemd services and background operations
- **Diagnostics Feed**: Live warnings and errors from system logs
- **Command Runner**: Execute shell commands securely (optional, disabled by default)
- **Web Interface**: Modern React-based web dashboard

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/Exios66/COMMAND_UI.git
cd COMMAND_UI

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

## Usage

### Terminal UI

Run the terminal interface:

```bash
diagterm
```

Options:

- `-r, --refresh INTERVAL`: Set refresh interval in seconds (default: 1.0)
- `Ctrl+R`: Manual refresh
- `Ctrl+L`: Clear command log
- `Ctrl+C`: Quit

### Web Interface

Start the web server:

```bash
diagterm-web
```

Then open your browser to:

- **Local**: <http://127.0.0.1:8765/>
- **GitHub Pages**: <https://exios66.github.io/COMMAND_UI/>

#### Environment Variables

- `DIAGTERM_WEB_HOST`: Server host (default: `127.0.0.1`)
- `DIAGTERM_WEB_PORT`: Server port (default: `8765`)
- `DIAGTERM_WEB_ENABLE_RUNNER`: Enable command runner (set to `1` to enable, default: disabled for security)

#### Building the Frontend

If you need to rebuild the frontend:

```bash
cd docs
npm install
npm run build
```

For development with hot reload:

```bash
cd docs
npm install
npm run dev
```

## GitHub Pages Deployment

The web interface is automatically deployed to GitHub Pages via GitHub Actions.

### Setup

1. **Enable GitHub Pages:**
   - Go to repository Settings → Pages
   - Under "Source", select "GitHub Actions"
   - Save the settings

2. **Deploy:**
   - Push to the `main` branch
   - The workflow (`.github/workflows/deploy-pages.yml`) will automatically build and deploy
   - Your site will be available at: `https://exios66.github.io/COMMAND_UI/`

### Manual Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed deployment instructions.

## API Endpoints

The web server provides the following API endpoints:

- `GET /api/summary` - System summary (CPU, memory, disk, network)
- `GET /api/processes?limit=25` - Top processes
- `GET /api/services?limit=25` - Running services
- `GET /api/diagnostics?limit=120` - Diagnostics feed
- `POST /api/run` - Run command (requires `DIAGTERM_WEB_ENABLE_RUNNER=1`)

## Requirements

- Python 3.9+
- Node.js 20+ (for web frontend development)
- Linux/macOS (Windows support is limited)

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Links

- **GitHub Repository**: <https://github.com/Exios66/COMMAND_UI>
- **GitHub Pages**: <https://exios66.github.io/COMMAND_UI/>
- **Issues**: <https://github.com/Exios66/COMMAND_UI/issues>
