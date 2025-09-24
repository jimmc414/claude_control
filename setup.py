#!/usr/bin/env python3
"""
Setup script for claudecontrol
Minimal installation with smart defaults
"""

import os
import sys
from pathlib import Path
from setuptools import setup, find_packages

# Read version from package
version = "0.1.0"

# Minimal dependencies - just what we absolutely need
install_requires = [
    "pexpect>=4.8.0",
    "psutil>=5.9.0",  # For zombie process cleanup
    "pyjson5>=1.6.9",
    "fastjsonschema>=2.20",
    "portalocker>=2.8",
]

# Optional dependencies for enhanced features
extras_require = {
    "watch": ["watchdog>=2.1.0"],  # For efficient file monitoring
    "dev": [
        "pytest>=7.0.0",
        "pytest-asyncio>=0.18.0",
        "black>=22.0.0",
        "mypy>=0.950",
    ],
}

setup(
    name="claudecontrol",
    version=version,
    description="Give Claude control of your terminal - Elegant process automation",
    long_description=open("README.md").read() if Path("README.md").exists() else "",
    long_description_content_type="text/markdown",
    author="Claude Code User",
    python_requires=">=3.8",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=install_requires,
    extras_require=extras_require,
    entry_points={
        "console_scripts": [
            "claude-control=claudecontrol.cli:main",
            "ccontrol=claudecontrol.cli:main",  # Short alias
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Testing",
        "Topic :: System :: Shells",
    ],
)

def post_install():
    """Run post-installation setup"""
    # Create directories with proper permissions
    base_dir = Path.home() / ".claude-control"
    dirs_to_create = [
        base_dir / "sessions",
        base_dir / "logs", 
        base_dir / "commands",
        base_dir / "responses",
    ]
    
    for dir_path in dirs_to_create:
        dir_path.mkdir(parents=True, exist_ok=True)
        # Set user-only permissions
        os.chmod(dir_path, 0o700)
    
    # Create default config if it doesn't exist
    config_file = base_dir / "config.json"
    if not config_file.exists():
        import json
        default_config = {
            "session_timeout": 300,  # 5 minutes
            "max_sessions": 20,
            "auto_cleanup": True,
            "log_level": "INFO",
        }
        config_file.write_text(json.dumps(default_config, indent=2))
        os.chmod(config_file, 0o600)
    
    print(f"✓ Created configuration directory at {base_dir}")
    print("✓ Installation complete!")
    print("\nQuick start:")
    print("  python -m claudecontrol.examples.simple")
    print("  ccontrol --help")

# Run post-install if this is being run directly
if __name__ == "__main__" and "install" in sys.argv:
    from setuptools.command.install import install
    
    class PostInstallCommand(install):
        def run(self):
            install.run(self)
            post_install()
    
    setup(cmdclass={"install": PostInstallCommand})