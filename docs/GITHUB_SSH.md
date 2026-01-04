## 🔐 Cloning a Private GitHub Repository (with Submodules)

Because this repository is **private**, you must authenticate with GitHub before cloning. The recommended method is **SSH authentication**.

### ✅ Prerequisites

1. **GitHub account with access** to the `LCAS-Lab/TnTechIGVC2026` repository
2. **SSH key registered with GitHub**

---

### 🔑 Step 1 — Check for an Existing SSH Key

```bash
ls ~/.ssh
```

If you see files like `id_rsa.pub`, `id_ed25519.pub`, or similar, you likely already have an SSH key.

---

### 🔑 Step 2 — Generate an SSH Key (if needed)

```bash
ssh-keygen -t ed25519 -C "your_email@domain.com"
```

Press **Enter** to accept defaults.

---

### 🔑 Step 3 — Add the SSH Key to GitHub

Copy the public key:

```bash
cat ~/.ssh/id_ed25519.pub
```

Then add it to GitHub:

GitHub → **Settings** → **SSH and GPG keys** → **New SSH key**

---

### 🔑 Step 4 — Verify GitHub SSH Access

```bash
ssh -T git@github.com
```

Expected message:

```
Hi <username>! You've successfully authenticated, but GitHub does not provide shell access.
```

---

### 📦 Step 5 — Clone the Repository (SSH)

Use the **SSH URL**, not HTTPS:

```bash
git clone --recurse-submodules git@github.com:LCAS-Lab/TnTechIGVC2026.git
cd TnTechIGVC2026
git lfs pull
```

> **Important:** Submodules inherit the same authentication method. If submodules are private, SSH must be configured correctly or the clone will fail.

---

### ⚠️ Common Pitfalls

* Cloning via **HTTPS** will prompt for a **Personal Access Token (PAT)** instead of a password
* Mixing HTTPS and SSH URLs can cause submodule authentication failures
* Missing `git lfs pull` will result in incomplete large files

---

### ✅ Recommendation for Lab Machines / Jetson Systems

For development machines, Jetsons, and Docker hosts:

* Use **SSH authentication**
* Ensure keys are **non-interactive**
* Avoid HTTPS + PAT in automated workflows