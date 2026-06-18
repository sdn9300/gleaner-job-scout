# User Manual: How to Find Jobs with Gleaner

This manual describes how to use **Gleaner** to automatically find and aggregate job openings for specific job roles.
Using Gleaner, you can run a simple command that gathers jobs from Naukri, RemoteOK, Indeed, and Wellfound, and exports them directly into a local Excel-compatible file (CSV) or a Google Sheet.

---

## Step 1: Install Python on Your Computer

Gleaner is written in **Python**. You need to install Python to run it.

1. Go to the official website: [python.org/downloads](https://www.python.org/downloads/).
2. Download the latest version of Python (version 3.10 or higher is recommended).
3. **Crucial Step (Windows)**: When running the installer, make sure to check the box that says **"Add Python.exe to PATH"** before clicking Install.
4. Open your computer's terminal:
   - **Windows**: Search for `cmd` or `PowerShell` in the Start menu.
   - **Mac/Linux**: Open the `Terminal` application.
5. Verify the installation by typing this command and pressing Enter:
   ```bash
   python --version
   ```
   If it shows something like `Python 3.10.x` or higher, you are ready to go!

---

## Step 2: Download Gleaner and Install Dependencies

1. Download this project to your computer. (If you use Git, run `git clone https://github.com/sdn9300/gleaner-job-scout.git`).
2. Open your terminal and navigate to the folder where you downloaded this project. For example:
   ```powershell
   cd "C:\My Projects\Job Scraping"
   ```
3. Install the software packages Gleaner needs to run by typing:
   ```bash
   pip install -r requirements.txt
   ```
   *Wait for the progress bars to finish.*

---

## Step 3: Get API Keys and Setup Configuration

To fetch jobs and write to Google Sheets, you need to set up credentials.

### A. Get a Firecrawl API Key (For scraping)
1. Go to [firecrawl.dev](https://www.firecrawl.dev/) and sign up for a free account.
2. Go to your dashboard and copy your **API Key** (it starts with `fc-`).

### B. Setup your environment file
1. In the main project folder, locate the file named `.env.example`.
2. Rename this file to exactly `.env`.
3. Open it with any text editor (like Notepad) and paste your Firecrawl API key:
   ```ini
   FIRECRAWL_API_KEY=fc-your-actual-api-key-here
   GOOGLE_SERVICE_ACCOUNT_JSON=credentials/service_account.json
   ```

---

## Step 4: Scraping Jobs to Local Excel (CSV)

CSV files open automatically in **Microsoft Excel**, **Google Sheets**, or **Numbers**.

### Example 1: Finding "Data Scientist" jobs in "Bangalore"
Run this command in your terminal:
```bash
python gleaner.py --role "Data Scientist" --location "Bangalore" --output datascientist_bangalore.csv
```

### Example 2: Finding "Data Analyst" remote jobs
```bash
python gleaner.py --role "Data Analyst" --location "Remote" --output remote_data_analysts.csv
```

### Example 3: Finding "AI Engineer" jobs from specific sites
If you only want to search on **RemoteOK** and **Wellfound**, use the `--boards` flag:
```bash
python gleaner.py --role "AI Engineer" --location "Remote" --boards "remoteok,wellfound" --output ai_engineers.csv
```

**How to open in Excel:**
1. Locate the generated `.csv` file in your project directory.
2. Double-click it. Excel will open it as a structured spreadsheet with columns: `Title`, `Company`, `Location`, `Source`, `URL`, etc.

---

## Step 5: Syncing Directly to a Google Sheet (Optional)

If you want the jobs automatically updated in a live Google Sheet:

### 1. Set Up Google Cloud Credentials
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable the **Google Sheets API** and **Google Drive API**.
3. Create a **Service Account** and download its key as a JSON file.
4. Create a folder named `credentials` in the project folder.
5. Move the downloaded JSON file into `credentials/` and rename it to `service_account.json`.

### 2. Prepare the Google Sheet
1. Open Google Sheets and create a new, blank sheet.
2. Copy the **email address of your Service Account** (you can find this in your Google Cloud dashboard or inside the `service_account.json` file—it looks like `account-name@project-id.iam.gserviceaccount.com`).
3. Click the **Share** button on your Google Sheet and share it with that Service Account email address as an **Editor**.

### 3. Run the Scraping Command
Pass your Google Sheet's URL using the `--sheet` flag:
```bash
python gleaner.py --role "AI Engineer" --location "Remote" --sheet "https://docs.google.com/spreadsheets/d/your-sheet-id/edit"
```
Once completed, open your browser—you will see the Google Sheet instantly populated with the cleaned job search results!

---

## Troubleshooting

- **Error: `ModuleNotFoundError`**: Run `pip install -r requirements.txt` again.
- **No jobs found**: Some websites block frequent requests. Wait a couple of minutes, or double-check that your spelling of `--role` matches common job descriptions.
- **Firecrawl API Error**: Verify that the `FIRECRAWL_API_KEY` in your `.env` file is correct and active.
