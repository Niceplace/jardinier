# Jardinier

Jardinier extracts transactions from Desjardins banking statements (credit card and checking account PDFs) and imports them into [Firefly-III](https://www.firefly-iii.org/), a self-hosted personal finance manager. It parses transaction details including amounts, dates, merchant names, refunds, foreign currency, and maps them to the correct Firefly-III transaction types (withdrawals, deposits, transfers).

**This project is not affiliated with Desjardins, Firefly-III, or any financial institution. It is an independent, volunteer-driven effort by people who want to use self-hosted budgeting software with their bank statements.**

## Installation

- **pip:** `pip install jardinier`
- **uv:** `uv tool install jardinier`
- **From source:** `git clone <repo-url> && cd jardinier && uv sync --all-extras --dev`

## Usage

> Note: This setup assumes you already did some basic setup in firefly-iii to configure asset accounts and liability accounts. These accounts will be used to determine where the money comes from and where it goes. The CLI does not create them for you but it can read firefly-iii's API and fetch existing ones so you can pick.

- `jardinier upload statement.pdf --type CC` — extract and import a single credit card statement
- `jardinier upload statement.pdf --type ACCT` — extract and import a checking account statement
- `jardinier batch ./pdfs --type CC` — process all PDFs in a folder
- `jardinier validate statement.pdf --type CC` — extract and display without uploading
- Account IDs are optional; if omitted, you'll be prompted to select from your Firefly-III asset accounts
- Requires `FIREFLY_API_URL` and `FIREFLY_API_TOKEN` — create `~/.config/jardinier/.env` (recommended), export them as env vars, or place a `.env` in the directory you run the CLI from

## CLI Reference

_Just watch how fast this becomes outdated_

```
Usage: jardinier [OPTIONS] COMMAND [ARGS]...

  Jardinier - Process Desjardins statements and sync to Firefly-III.

Options:
  --version        Show the version and exit.
  --json           Output results in JSON format
  -v, --verbose    Enable verbose logging
  --log-file PATH  Path to log file (default:
                   ~/.local/share/jardinier/logs/jardinier.log)
  --help           Show this message and exit.

Commands:
  batch     Process all PDFs in a folder.
  upload    Upload a single PDF statement to Firefly-III.
  validate  Validate PDF and show extracted data (no upload).
```

```
Usage: jardinier upload [OPTIONS] PDF

  Upload a single PDF statement to Firefly-III.

Options:
  --type [CC|ACCT]               [required]
  --cc-account-id INTEGER        Firefly-III asset account ID for credit card
  --checking-account-id INTEGER  Firefly-III asset account ID for checking
                                 account
  --expense-account-id INTEGER   Firefly-III expense account ID for all
                                 withdrawals (CC only)
  --loc-account-id INTEGER       Firefly-III liability account ID for line of
                                 credit (ACCT only)
  --mortgage-account-id INTEGER  Firefly-III liability account ID for mortgage
                                 (ACCT only)
  --start-date TEXT              Statement period start date (YYYY-MM-DD, ACCT
                                 only)
  --end-date TEXT                Statement period end date (YYYY-MM-DD, ACCT
                                 only)
  --dry-run                      Validate and extract without uploading to
                                 Firefly-III
  --help                         Show this message and exit.
```

```
Usage: jardinier batch [OPTIONS] FOLDER

  Process all PDFs in a folder.

Options:
  --type [CC|ACCT]               [required]
  --cc-account-id INTEGER        Firefly-III asset account ID for credit card
  --checking-account-id INTEGER  Firefly-III asset account ID for checking
                                 account
  --expense-account-id INTEGER   Firefly-III expense account ID for all
                                 withdrawals
  --loc-account-id INTEGER       Firefly-III liability account ID for line of
                                 credit
  --mortgage-account-id INTEGER  Firefly-III liability account ID for mortgage
  --fail-fast                    Stop processing on first error
  --dry-run
  --help                         Show this message and exit.
```

```
Usage: jardinier validate [OPTIONS] PDF

  Validate PDF and show extracted data (no upload).

Options:
  --type [CC|ACCT]   [required]
  --start-date TEXT  Statement period start date (YYYY-MM-DD, ACCT only)
  --end-date TEXT    Statement period end date (YYYY-MM-DD, ACCT only)
  --help             Show this message and exit.
```

Do you want to join me on this _fascinating_ adventure ? Read [CONTRIBUTING.md](./CONTRIBUTING.md) for development setup, guidelines, and please have a good look at community rules. I'm waiting :)

# FAQ

# Has this been vibe co-

Yes. Yes it has. If I had taken on the challenge of parsing my bank's PDFs manually I would still be doing it in 2028 full time. However, I do rigorous dog-fooding and I use the software myself, so you can expect _some_ level of quality.

# What banks does this support ?

So far, Desjardins (because it's my bank). Support for other banks might be hard unless I can get my hands on bank account/credit card statements, so don't expect this to happen quickly unless you want to propose something.

# What are you planning next ?

- Validation-helper CLI -> The parsing of PDFs has been tested a lot, but it's not perfect, so I'm sure there are some transactions that are not being properly parsed. I want to have an interactive command that helps me check random transactions here and there so I can provide the real information by reading the statement, and have the CLI re-parse it and check that the info matches
- Account name consolidation -> The resulting account names in firefly-iii, especially for credit card transactions can result in a bunch of "duplicates" or differently named entries that all point to the same business. I plan to add a functionality to review all existing expense accounts in firefly-iii and use "natural" language processing features to consolidate all of these so the naming is as consistent as possible. Some sort of an automated helper to ensure we have as little unique account names as possible or unclassified transactions
