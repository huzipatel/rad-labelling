#!/usr/bin/env python3
"""
GSV API Key Manager - Web UI

A simple web interface to manage multiple Google accounts and API keys
for high-throughput Street View image downloads.

Run: python web_ui.py
Then open: http://localhost:5000
"""

import subprocess
import json
import os
import threading
import time
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request

app = Flask(__name__)

# Data storage
DATA_FILE = "accounts_data.json"
LOCK = threading.Lock()

# Default settings
DEFAULT_PROJECTS_PER_ACCOUNT = 30
IMAGES_PER_PROJECT_PER_DAY = 25000


def load_data():
    """Load saved data."""
    if Path(DATA_FILE).exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"accounts": [], "settings": {"projects_per_account": DEFAULT_PROJECTS_PER_ACCOUNT}}


def save_data(data):
    """Save data to file."""
    with LOCK:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)


def run_gcloud(cmd, account_email=None):
    """Run a gcloud command, optionally with a specific account."""
    if account_email:
        cmd = ["gcloud", "--account", account_email] + cmd[1:]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


# HTML Template with modern UI
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GSV API Key Manager</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 24px;
        }
        
        header {
            text-align: center;
            padding: 32px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 32px;
        }
        
        h1 {
            font-size: 2.5rem;
            background: linear-gradient(135deg, #00d4ff, #7c3aed);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }
        
        .subtitle {
            color: #888;
            font-size: 1.1rem;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 32px;
        }
        
        .stat-card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 24px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 2.5rem;
            font-weight: 700;
            color: #00d4ff;
        }
        
        .stat-value.green { color: #10b981; }
        .stat-value.purple { color: #7c3aed; }
        .stat-value.orange { color: #f59e0b; }
        
        .stat-label {
            color: #888;
            margin-top: 8px;
            font-size: 0.9rem;
        }
        
        .section {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
        }
        
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .section-title {
            font-size: 1.3rem;
            font-weight: 600;
        }
        
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.95rem;
            transition: all 0.2s;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #00d4ff, #0099cc);
            color: white;
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 20px rgba(0, 212, 255, 0.3);
        }
        
        .btn-success {
            background: linear-gradient(135deg, #10b981, #059669);
            color: white;
        }
        
        .btn-warning {
            background: linear-gradient(135deg, #f59e0b, #d97706);
            color: white;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, #ef4444, #dc2626);
            color: white;
        }
        
        .btn-secondary {
            background: rgba(255,255,255,0.1);
            color: #e0e0e0;
            border: 1px solid rgba(255,255,255,0.2);
        }
        
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .account-card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
        }
        
        .account-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }
        
        .account-email {
            font-weight: 600;
            color: #00d4ff;
        }
        
        .account-status {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
        }
        
        .status-active {
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
        }
        
        .status-pending {
            background: rgba(245, 158, 11, 0.2);
            color: #f59e0b;
        }
        
        .progress-bar {
            height: 8px;
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
            overflow: hidden;
            margin: 12px 0;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #00d4ff, #7c3aed);
            border-radius: 4px;
            transition: width 0.3s;
        }
        
        .input-group {
            margin-bottom: 16px;
        }
        
        .input-group label {
            display: block;
            margin-bottom: 8px;
            color: #888;
        }
        
        .input-group input, .input-group select {
            width: 100%;
            padding: 12px 16px;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            background: rgba(255,255,255,0.05);
            color: #e0e0e0;
            font-size: 1rem;
        }
        
        .input-group input:focus {
            outline: none;
            border-color: #00d4ff;
        }
        
        .keys-output {
            background: #0d1117;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 8px;
            padding: 16px;
            font-family: 'Consolas', monospace;
            font-size: 0.85rem;
            max-height: 200px;
            overflow-y: auto;
            word-break: break-all;
        }
        
        .copy-btn {
            margin-top: 12px;
        }
        
        .log-output {
            background: #0d1117;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 8px;
            padding: 16px;
            font-family: 'Consolas', monospace;
            font-size: 0.85rem;
            max-height: 300px;
            overflow-y: auto;
            white-space: pre-wrap;
        }
        
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }
        
        .modal.active {
            display: flex;
        }
        
        .modal-content {
            background: #1a1a2e;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 32px;
            max-width: 500px;
            width: 90%;
        }
        
        .modal-header {
            margin-bottom: 24px;
        }
        
        .modal-title {
            font-size: 1.5rem;
            margin-bottom: 8px;
        }
        
        .btn-group {
            display: flex;
            gap: 12px;
            margin-top: 24px;
        }
        
        .alert {
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 16px;
        }
        
        .alert-info {
            background: rgba(0, 212, 255, 0.1);
            border: 1px solid rgba(0, 212, 255, 0.3);
            color: #00d4ff;
        }
        
        .alert-success {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: #10b981;
        }
        
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid rgba(255,255,255,0.3);
            border-top-color: #00d4ff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-right: 8px;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .instructions {
            background: rgba(124, 58, 237, 0.1);
            border: 1px solid rgba(124, 58, 237, 0.3);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }
        
        .instructions h3 {
            color: #7c3aed;
            margin-bottom: 12px;
        }
        
        .instructions ol {
            margin-left: 20px;
            color: #ccc;
        }
        
        .instructions li {
            margin-bottom: 8px;
        }
        
        .instructions code {
            background: rgba(255,255,255,0.1);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Consolas', monospace;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔑 GSV API Key Manager</h1>
            <p class="subtitle">Manage multiple Google accounts for high-throughput Street View downloads</p>
        </header>
        
        <!-- Stats -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value" id="totalAccounts">0</div>
                <div class="stat-label">Accounts</div>
            </div>
            <div class="stat-card">
                <div class="stat-value green" id="totalProjects">0</div>
                <div class="stat-label">Projects</div>
            </div>
            <div class="stat-card">
                <div class="stat-value purple" id="totalKeys">0</div>
                <div class="stat-label">API Keys</div>
            </div>
            <div class="stat-card">
                <div class="stat-value orange" id="dailyCapacity">0</div>
                <div class="stat-label">Images/Day</div>
            </div>
        </div>
        
        <!-- Instructions -->
        <div class="instructions">
            <h3>📋 Quick Start</h3>
            <ol>
                <li>Run <code>gcloud auth login</code> in terminal for each Google account you want to use</li>
                <li>Click "Add Account" and enter the email for each authenticated account</li>
                <li>Set the billing account ID for each account</li>
                <li>Click "Create Projects" to generate 30 projects per account</li>
                <li>Copy all keys to your Render <code>GSV_API_KEYS</code> environment variable</li>
            </ol>
        </div>
        
        <!-- Accounts Section -->
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">👤 Google Accounts</h2>
                <button class="btn btn-primary" onclick="showAddAccountModal()">+ Add Account</button>
            </div>
            <div id="accountsList"></div>
        </div>
        
        <!-- API Keys Section -->
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">🔑 All API Keys</h2>
                <button class="btn btn-success" onclick="copyAllKeys()">📋 Copy All Keys</button>
            </div>
            <div class="keys-output" id="allKeysOutput">No keys yet. Add accounts and create projects to generate keys.</div>
            <div style="margin-top: 16px; display: flex; gap: 12px;">
                <button class="btn btn-secondary" onclick="refreshAllKeys()">🔄 Refresh Keys</button>
                <button class="btn btn-primary" onclick="createAllProjects()">🚀 Create All Projects</button>
            </div>
        </div>
        
        <!-- Logs Section -->
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">📜 Activity Log</h2>
                <button class="btn btn-secondary" onclick="clearLogs()">Clear</button>
            </div>
            <div class="log-output" id="logOutput">Ready to start...</div>
        </div>
    </div>
    
    <!-- Add Account Modal -->
    <div class="modal" id="addAccountModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 class="modal-title">Add Google Account</h2>
                <p style="color: #888;">First run <code>gcloud auth login</code> in terminal, then add the account here.</p>
            </div>
            <div class="input-group">
                <label>Google Account Email</label>
                <input type="email" id="accountEmail" placeholder="your-email@gmail.com">
            </div>
            <div class="input-group">
                <label>Billing Account ID</label>
                <input type="text" id="billingAccountId" placeholder="XXXXXX-XXXXXX-XXXXXX">
                <small style="color: #888;">Run <code>gcloud billing accounts list</code> to find this</small>
            </div>
            <div class="input-group">
                <label>Projects to Create</label>
                <input type="number" id="projectsCount" value="30" min="1" max="50">
            </div>
            <div class="btn-group">
                <button class="btn btn-secondary" onclick="hideAddAccountModal()">Cancel</button>
                <button class="btn btn-primary" onclick="addAccount()">Add Account</button>
            </div>
        </div>
    </div>
    
    <script>
        let data = { accounts: [], settings: {} };
        
        // Load data on page load
        async function loadData() {
            try {
                const response = await fetch('/api/data');
                data = await response.json();
                updateUI();
            } catch (e) {
                log('Error loading data: ' + e.message, 'error');
            }
        }
        
        function updateUI() {
            // Update stats
            const totalAccounts = data.accounts.length;
            const totalProjects = data.accounts.reduce((sum, a) => sum + (a.projects?.length || 0), 0);
            const totalKeys = data.accounts.reduce((sum, a) => 
                sum + (a.projects?.filter(p => p.api_key)?.length || 0), 0);
            const dailyCapacity = totalKeys * 25000;
            
            document.getElementById('totalAccounts').textContent = totalAccounts;
            document.getElementById('totalProjects').textContent = totalProjects;
            document.getElementById('totalKeys').textContent = totalKeys;
            document.getElementById('dailyCapacity').textContent = dailyCapacity.toLocaleString();
            
            // Update accounts list
            const accountsList = document.getElementById('accountsList');
            if (data.accounts.length === 0) {
                accountsList.innerHTML = '<p style="color: #888; text-align: center; padding: 40px;">No accounts added yet. Click "Add Account" to get started.</p>';
            } else {
                accountsList.innerHTML = data.accounts.map(renderAccount).join('');
            }
            
            // Update keys output
            const allKeys = data.accounts.flatMap(a => 
                (a.projects || []).filter(p => p.api_key).map(p => p.api_key)
            );
            document.getElementById('allKeysOutput').textContent = 
                allKeys.length > 0 ? allKeys.join(',') : 'No keys yet. Add accounts and create projects to generate keys.';
        }
        
        function renderAccount(account, index) {
            const projects = account.projects || [];
            const keysCount = projects.filter(p => p.api_key).length;
            const progress = account.target_projects > 0 ? (projects.length / account.target_projects * 100) : 0;
            
            return `
                <div class="account-card">
                    <div class="account-header">
                        <div>
                            <div class="account-email">${account.email}</div>
                            <small style="color: #888;">Billing: ${account.billing_id || 'Not set'}</small>
                        </div>
                        <div>
                            <span class="account-status ${keysCount > 0 ? 'status-active' : 'status-pending'}">
                                ${keysCount}/${account.target_projects || 30} keys
                            </span>
                        </div>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${progress}%"></div>
                    </div>
                    <div style="display: flex; gap: 8px; margin-top: 12px;">
                        <button class="btn btn-primary btn-sm" onclick="createProjectsForAccount(${index})" 
                            ${account.creating ? 'disabled' : ''}>
                            ${account.creating ? '<span class="spinner"></span>Creating...' : '🚀 Create Projects'}
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="refreshAccountKeys(${index})">🔄 Refresh</button>
                        <button class="btn btn-danger btn-sm" onclick="removeAccount(${index})">🗑️ Remove</button>
                    </div>
                </div>
            `;
        }
        
        function log(message, type = 'info') {
            const logOutput = document.getElementById('logOutput');
            const timestamp = new Date().toLocaleTimeString();
            const prefix = type === 'error' ? '❌' : type === 'success' ? '✅' : 'ℹ️';
            logOutput.textContent = `[${timestamp}] ${prefix} ${message}\\n` + logOutput.textContent;
        }
        
        function clearLogs() {
            document.getElementById('logOutput').textContent = 'Logs cleared.';
        }
        
        function showAddAccountModal() {
            document.getElementById('addAccountModal').classList.add('active');
        }
        
        function hideAddAccountModal() {
            document.getElementById('addAccountModal').classList.remove('active');
        }
        
        async function addAccount() {
            const email = document.getElementById('accountEmail').value.trim();
            const billingId = document.getElementById('billingAccountId').value.trim();
            const projectsCount = parseInt(document.getElementById('projectsCount').value) || 30;
            
            if (!email) {
                alert('Please enter an email address');
                return;
            }
            
            try {
                const response = await fetch('/api/accounts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, billing_id: billingId, target_projects: projectsCount })
                });
                
                const result = await response.json();
                if (result.success) {
                    log(`Added account: ${email}`, 'success');
                    hideAddAccountModal();
                    document.getElementById('accountEmail').value = '';
                    document.getElementById('billingAccountId').value = '';
                    loadData();
                } else {
                    log(`Failed to add account: ${result.error}`, 'error');
                }
            } catch (e) {
                log('Error adding account: ' + e.message, 'error');
            }
        }
        
        async function removeAccount(index) {
            if (!confirm('Remove this account and all its projects?')) return;
            
            try {
                const response = await fetch(`/api/accounts/${index}`, { method: 'DELETE' });
                const result = await response.json();
                if (result.success) {
                    log('Account removed', 'success');
                    loadData();
                }
            } catch (e) {
                log('Error removing account: ' + e.message, 'error');
            }
        }
        
        async function createProjectsForAccount(index) {
            log(`Starting project creation for account ${index + 1}...`);
            
            try {
                const response = await fetch(`/api/accounts/${index}/create-projects`, { method: 'POST' });
                const result = await response.json();
                
                if (result.success) {
                    log(`Created ${result.created} projects with ${result.keys} keys`, 'success');
                } else {
                    log(`Error: ${result.error}`, 'error');
                }
                loadData();
            } catch (e) {
                log('Error creating projects: ' + e.message, 'error');
            }
        }
        
        async function createAllProjects() {
            if (!confirm('Create projects for ALL accounts? This may take a while.')) return;
            
            for (let i = 0; i < data.accounts.length; i++) {
                await createProjectsForAccount(i);
            }
            
            log('All projects created!', 'success');
        }
        
        async function refreshAccountKeys(index) {
            log(`Refreshing keys for account ${index + 1}...`);
            
            try {
                const response = await fetch(`/api/accounts/${index}/refresh-keys`, { method: 'POST' });
                const result = await response.json();
                
                if (result.success) {
                    log(`Refreshed ${result.keys} keys`, 'success');
                } else {
                    log(`Error: ${result.error}`, 'error');
                }
                loadData();
            } catch (e) {
                log('Error refreshing keys: ' + e.message, 'error');
            }
        }
        
        async function refreshAllKeys() {
            log('Refreshing all keys...');
            for (let i = 0; i < data.accounts.length; i++) {
                await refreshAccountKeys(i);
            }
            log('All keys refreshed!', 'success');
        }
        
        function copyAllKeys() {
            const keysOutput = document.getElementById('allKeysOutput').textContent;
            if (keysOutput.includes('No keys yet')) {
                alert('No keys to copy yet!');
                return;
            }
            
            navigator.clipboard.writeText(keysOutput).then(() => {
                log('All keys copied to clipboard!', 'success');
                alert('Keys copied to clipboard! Paste into Render GSV_API_KEYS environment variable.');
            });
        }
        
        // Load data on page load
        loadData();
        
        // Auto-refresh every 10 seconds
        setInterval(loadData, 10000);
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/data')
def get_data():
    return jsonify(load_data())


@app.route('/api/accounts', methods=['POST'])
def add_account():
    try:
        req_data = request.json
        email = req_data.get('email', '').strip()
        billing_id = req_data.get('billing_id', '').strip()
        target_projects = req_data.get('target_projects', 30)
        
        if not email:
            return jsonify({"success": False, "error": "Email required"})
        
        data = load_data()
        
        # Check if account already exists
        if any(a['email'] == email for a in data['accounts']):
            return jsonify({"success": False, "error": "Account already exists"})
        
        data['accounts'].append({
            "email": email,
            "billing_id": billing_id,
            "target_projects": target_projects,
            "projects": [],
            "created_at": datetime.now().isoformat()
        })
        
        save_data(data)
        return jsonify({"success": True})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/accounts/<int:index>', methods=['DELETE'])
def remove_account(index):
    try:
        data = load_data()
        if 0 <= index < len(data['accounts']):
            del data['accounts'][index]
            save_data(data)
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Account not found"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/accounts/<int:index>/create-projects', methods=['POST'])
def create_projects_for_account(index):
    try:
        data = load_data()
        if index >= len(data['accounts']):
            return jsonify({"success": False, "error": "Account not found"})
        
        account = data['accounts'][index]
        email = account['email']
        billing_id = account.get('billing_id', '')
        target = account.get('target_projects', 30)
        existing_projects = {p['project_id'] for p in account.get('projects', [])}
        
        created = 0
        keys_created = 0
        
        for i in range(1, target + 1):
            project_id = f"gsv-{email.split('@')[0][:10]}-{i}"
            
            if project_id in existing_projects:
                continue
            
            # Create project
            success, _, error = run_gcloud([
                "gcloud", "projects", "create", project_id,
                "--name", f"GSV {i}"
            ], email)
            
            if not success and "already exists" not in error.lower():
                continue
            
            # Link billing
            if billing_id:
                run_gcloud([
                    "gcloud", "billing", "projects", "link", project_id,
                    "--billing-account", billing_id
                ], email)
            
            # Enable API
            run_gcloud([
                "gcloud", "services", "enable",
                "streetviewpublish.googleapis.com",
                "--project", project_id
            ], email)
            
            # Create API key
            success, output, _ = run_gcloud([
                "gcloud", "services", "api-keys", "create",
                "--project", project_id,
                "--display-name", f"GSV-Key-{i}",
                "--format=json"
            ], email)
            
            api_key = None
            if success:
                try:
                    key_data = json.loads(output)
                    api_key = key_data.get("keyString")
                except:
                    pass
            
            # If we couldn't get key from create, try to list
            if not api_key:
                success, output, _ = run_gcloud([
                    "gcloud", "services", "api-keys", "list",
                    "--project", project_id,
                    "--format=json"
                ], email)
                
                if success:
                    try:
                        keys = json.loads(output)
                        if keys:
                            key_name = keys[0].get("name", "")
                            if key_name:
                                success, output, _ = run_gcloud([
                                    "gcloud", "services", "api-keys", "get-key-string",
                                    key_name, "--format=json"
                                ], email)
                                if success:
                                    api_key = json.loads(output).get("keyString")
                    except:
                        pass
            
            account['projects'].append({
                "project_id": project_id,
                "api_key": api_key,
                "created_at": datetime.now().isoformat()
            })
            
            created += 1
            if api_key:
                keys_created += 1
            
            # Save progress
            save_data(data)
        
        return jsonify({"success": True, "created": created, "keys": keys_created})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/accounts/<int:index>/refresh-keys', methods=['POST'])
def refresh_account_keys(index):
    try:
        data = load_data()
        if index >= len(data['accounts']):
            return jsonify({"success": False, "error": "Account not found"})
        
        account = data['accounts'][index]
        email = account['email']
        keys_found = 0
        
        for project in account.get('projects', []):
            project_id = project['project_id']
            
            success, output, _ = run_gcloud([
                "gcloud", "services", "api-keys", "list",
                "--project", project_id,
                "--format=json"
            ], email)
            
            if success:
                try:
                    keys = json.loads(output)
                    if keys:
                        key_name = keys[0].get("name", "")
                        if key_name:
                            success, output, _ = run_gcloud([
                                "gcloud", "services", "api-keys", "get-key-string",
                                key_name, "--format=json"
                            ], email)
                            if success:
                                api_key = json.loads(output).get("keyString")
                                if api_key:
                                    project['api_key'] = api_key
                                    keys_found += 1
                except:
                    pass
        
        save_data(data)
        return jsonify({"success": True, "keys": keys_found})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


if __name__ == '__main__':
    print("=" * 50)
    print("🔑 GSV API Key Manager")
    print("=" * 50)
    print("\nStarting web server...")
    print("Open http://localhost:5000 in your browser")
    print("\nPress Ctrl+C to stop\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)

