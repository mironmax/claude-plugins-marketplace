# GitHub Setup Instructions

Quick guide to publish your Knowledge Graph plugin to GitHub.

## Step 1: Create GitHub Repositories

Create two repositories on GitHub:

1. **knowledge-graph-plugin** - The plugin itself
2. **claude-plugins-marketplace** - Your plugin marketplace

## Step 2: Push Plugin Repository

```bash
cd ~/DevProj/knowledge-graph-plugin

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: Knowledge Graph plugin v1.0.0"

# Add GitHub remote (replace mironmax)
git remote add origin https://github.com/mironmax/knowledge-graph-plugin.git

# Push to GitHub
git push -u origin main
```

## Step 3: Push Marketplace Repository

```bash
cd ~/DevProj/claude-plugins-marketplace

# Update marketplace.json with your GitHub username
# Edit .claude-plugin/marketplace.json and replace mironmax

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: Maxim's plugins marketplace"

# Add GitHub remote (replace mironmax)
git remote add origin https://github.com/mironmax/claude-plugins-marketplace.git

# Push to GitHub
git push -u origin main
```

## Step 4: Update URLs

After creating repositories, update these files with your actual GitHub username:

**In knowledge-graph-plugin/README.md:**
- Replace `mironmax` with your GitHub username

**In claude-plugins-marketplace/README.md:**
- Replace `mironmax` with your GitHub username

**In claude-plugins-marketplace/.claude-plugin/marketplace.json:**
- Replace `mironmax` with your GitHub username in the source URL

Then commit and push the changes:

```bash
# In each repository
git add .
git commit -m "Update GitHub URLs"
git push
```

## Step 5: Test Installation

On any machine with Claude Code:

```bash
# Add your marketplace
/plugin marketplace add mironmax/claude-plugins-marketplace

# Install the plugin
/plugin install knowledge-graph@maxim-plugins

# Restart Claude Code
```

## Step 6: Share

Your plugin is now publicly available!

**Installation command users will run:**
```
/plugin marketplace add mironmax/claude-plugins-marketplace
/plugin install knowledge-graph@maxim-plugins
```

## Future Updates

When you update the plugin:

```bash
cd ~/DevProj/knowledge-graph-plugin

# Make changes...

# Update version in .claude-plugin/plugin.json
# Update version in README.md

git add .
git commit -m "Version X.Y.Z: Description of changes"
git tag vX.Y.Z
git push && git push --tags
```

Users can update via:
```
/plugin update knowledge-graph@maxim-plugins
```

(Or they may need to reinstall - check Claude Code docs for update mechanism)

## Troubleshooting

**Plugin not found:** Check marketplace.json has correct GitHub URL
**Installation fails:** Verify .claude-plugin/plugin.json is valid JSON
**Commands not loading:** Ensure commands/ directory is referenced in plugin.json
**MCP server not starting:** Check server/requirements.txt dependencies

## Repository Structure

```
knowledge-graph-plugin/          (Main plugin repo)
├── .claude-plugin/plugin.json
├── commands/
├── server/
├── skills/
├── scripts/
└── README.md

claude-plugins-marketplace/      (Marketplace repo)
├── .claude-plugin/marketplace.json
└── README.md
```

Both repos should be public for users to access them.
