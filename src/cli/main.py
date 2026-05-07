#!/usr/bin/env python3
"""
Jardinier CLI - Transformateur Desjardins
Command-line interface for processing Desjardins statements.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

import click

from app.account_extractor import AccountExtractor
from app.config import Config
from app.extractor import Extractor
from app.firefly import (
    FireflyClientError,
    build_batch,
    fetch_asset_accounts,
    map_account_transactions,
    map_bonidollars,
    map_transactions,
    send_batch,
)
from cli.date_inference import infer_dates_for_pdf
from cli.logging import setup_logging
from cli.output import OutputFormatter
from cli.validation import validate_account_id

BATCH_CHUNK_SIZE = 200


def _validate_env(config: Config, formatter: OutputFormatter):
    missing = []
    if not config.api_url:
        missing.append("FIREFLY_API_URL")
    if not config.api_token:
        missing.append("FIREFLY_API_TOKEN")
    if missing:
        formatter.error(f"Missing {' and '.join(missing)}. Choose one:")
        click.echo("")
        click.echo("  1. Create ~/.config/jardinier/.env (recommended, works from any directory)")
        click.echo("  2. Export them as environment variables: export FIREFLY_API_URL=... FIREFLY_API_TOKEN=...")
        click.echo("  3. Create a .env file in the directory you run jardinier from")
        click.echo("")
        click.echo("All three methods accept the same variables:")
        click.echo(f"  {' and '.join(missing)}")
        sys.exit(1)


def _prompt_account(
    accounts: List[Dict],
    label: str,
    formatter: OutputFormatter,
    optional: bool = False,
) -> Optional[int]:
    if not accounts:
        formatter.error("No asset accounts found in Firefly-III")
        return None

    suffix = " (press Enter to skip)" if optional else ""
    click.echo(f"\n{label}{suffix}:")
    for i, acct in enumerate(accounts, 1):
        click.echo(f"  [{i}] {acct['name']} (ID: {acct['id']})")

    while True:
        choice = click.prompt("Select account", default="", show_default=False)
        if not choice and optional:
            return None
        if not choice:
            click.echo("Please select an account.")
            continue
        try:
            idx = int(choice)
            if 1 <= idx <= len(accounts):
                return accounts[idx - 1]["id"]
            click.echo(f"Please enter a number between 1 and {len(accounts)}.")
        except ValueError:
            click.echo("Please enter a valid number.")


def _resolve_cc_accounts(
    api_url: str,
    api_token: str,
    formatter: OutputFormatter,
    cc_account_id: Optional[int] = None,
    checking_account_id: Optional[int] = None,
) -> Dict[str, Optional[int]]:
    accounts = fetch_asset_accounts(api_url=api_url, api_token=api_token)

    if cc_account_id is None:
        cc_account_id = _prompt_account(accounts, "Select the credit card account", formatter)
        if cc_account_id is None:
            formatter.error("Credit card account is required")
            sys.exit(1)

    if checking_account_id is None:
        checking_account_id = _prompt_account(
            accounts, "Select the account used for CC payments", formatter, optional=True
        )

    return {"cc_account_id": cc_account_id, "checking_account_id": checking_account_id}


def _resolve_acct_accounts(
    api_url: str,
    api_token: str,
    formatter: OutputFormatter,
    checking_account_id: Optional[int] = None,
    cc_account_id: Optional[int] = None,
    loc_account_id: Optional[int] = None,
    mortgage_account_id: Optional[int] = None,
) -> Dict[str, Optional[int]]:
    accounts = fetch_asset_accounts(api_url=api_url, api_token=api_token)

    if checking_account_id is None:
        checking_account_id = _prompt_account(accounts, "Select the checking account", formatter)
        if checking_account_id is None:
            formatter.error("Checking account is required")
            sys.exit(1)

    if cc_account_id is None:
        cc_account_id = _prompt_account(accounts, "Select the account used for CC payments", formatter, optional=True)

    if loc_account_id is None:
        loc_account_id = _prompt_account(accounts, "Select the line of credit account", formatter, optional=True)

    if mortgage_account_id is None:
        mortgage_account_id = _prompt_account(accounts, "Select the mortgage account", formatter, optional=True)

    return {
        "checking_account_id": checking_account_id,
        "cc_account_id": cc_account_id,
        "loc_account_id": loc_account_id,
        "mortgage_account_id": mortgage_account_id,
    }


@click.group()
@click.version_option(version="1.0.0")
@click.option("--json", is_flag=True, help="Output results in JSON format")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option(
    "--log-file",
    type=click.Path(),
    help="Path to log file (default: ~/.local/share/jardinier/logs/jardinier.log)",
)
@click.pass_context
def cli(ctx, json, verbose, log_file):
    """Jardinier - Process Desjardins statements and sync to Firefly-III."""
    logger = setup_logging(
        log_file=log_file or Path.home() / ".local" / "share" / "jardinier" / "logs" / "jardinier.log",
        verbose=verbose,
        json_output=json,
    )

    ctx.ensure_object(dict)
    ctx.obj["logger"] = logger
    ctx.obj["formatter"] = OutputFormatter(json_output=json, verbose=verbose)


@cli.command()
@click.argument("pdf", type=click.Path(exists=True))
@click.option("--type", type=click.Choice(["CC", "ACCT"]), required=True)
@click.option("--cc-account-id", type=int, help="Firefly-III asset account ID for credit card")
@click.option("--checking-account-id", type=int, help="Firefly-III asset account ID for checking account")
@click.option("--expense-account-id", type=int, help="Firefly-III expense account ID for all withdrawals (CC only)")
@click.option("--loc-account-id", type=int, help="Firefly-III liability account ID for line of credit (ACCT only)")
@click.option("--mortgage-account-id", type=int, help="Firefly-III liability account ID for mortgage (ACCT only)")
@click.option("--start-date", type=str, help="Statement period start date (YYYY-MM-DD, ACCT only)")
@click.option("--end-date", type=str, help="Statement period end date (YYYY-MM-DD, ACCT only)")
@click.option("--dry-run", is_flag=True, help="Validate and extract without uploading to Firefly-III")
@click.pass_context
def upload(ctx, pdf, type, cc_account_id, **kwargs):
    """Upload a single PDF statement to Firefly-III."""
    logger = ctx.obj["logger"]
    formatter = ctx.obj["formatter"]

    env_config = Config.from_env()

    if not kwargs.get("dry_run"):
        _validate_env(env_config, formatter)

        try:
            if type == "CC":
                resolved = _resolve_cc_accounts(
                    env_config.api_url,
                    env_config.api_token,
                    formatter,
                    cc_account_id=cc_account_id,
                    checking_account_id=kwargs.get("checking_account_id"),
                )
            else:
                resolved = _resolve_acct_accounts(
                    env_config.api_url,
                    env_config.api_token,
                    formatter,
                    checking_account_id=kwargs.get("checking_account_id"),
                    cc_account_id=cc_account_id,
                    loc_account_id=kwargs.get("loc_account_id"),
                    mortgage_account_id=kwargs.get("mortgage_account_id"),
                )
        except FireflyClientError as e:
            formatter.error(f"Could not connect to Firefly-III: {e}")
            sys.exit(1)

        cc_account_id = resolved.get("cc_account_id", cc_account_id)
        kwargs["checking_account_id"] = resolved.get("checking_account_id", kwargs.get("checking_account_id"))
        if "loc_account_id" in resolved:
            kwargs["loc_account_id"] = resolved["loc_account_id"]
        if "mortgage_account_id" in resolved:
            kwargs["mortgage_account_id"] = resolved["mortgage_account_id"]

    config = Config(
        api_url=env_config.api_url,
        api_token=env_config.api_token,
        cc_account_id=cc_account_id,
        checking_account_id=kwargs.get("checking_account_id"),
        expense_account_id=kwargs.get("expense_account_id"),
        loc_account_id=kwargs.get("loc_account_id"),
        mortgage_account_id=kwargs.get("mortgage_account_id"),
        start_date=kwargs.get("start_date"),
        end_date=kwargs.get("end_date"),
        dry_run=kwargs.get("dry_run", False),
    )

    if not config.dry_run:
        for account_id in [
            config.cc_account_id,
            config.checking_account_id,
            config.expense_account_id,
            config.loc_account_id,
            config.mortgage_account_id,
        ]:
            if account_id:
                valid, error = validate_account_id(account_id, config.api_url, config.api_token)
                if not valid:
                    formatter.error(error)
                    logger.error(f"Account validation failed: {error}")
                    sys.exit(1)

    try:
        pdf_path = Path(pdf).expanduser().resolve()
        if type == "CC":
            result = _process_cc(pdf_path, config, logger, formatter)
        else:
            result = _process_acct(pdf_path, config, logger, formatter)

        if result["success"]:
            sys.exit(0)
        else:
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


@cli.command()
@click.argument("folder", type=click.Path(exists=True, file_okay=False))
@click.option("--type", type=click.Choice(["CC", "ACCT"]), required=True)
@click.option("--cc-account-id", type=int, help="Firefly-III asset account ID for credit card")
@click.option("--checking-account-id", type=int, help="Firefly-III asset account ID for checking account")
@click.option("--expense-account-id", type=int, help="Firefly-III expense account ID for all withdrawals")
@click.option("--loc-account-id", type=int, help="Firefly-III liability account ID for line of credit")
@click.option("--mortgage-account-id", type=int, help="Firefly-III liability account ID for mortgage")
@click.option("--fail-fast", is_flag=True, default=False, help="Stop processing on first error")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def batch(
    ctx,
    folder,
    type,
    cc_account_id,
    checking_account_id,
    expense_account_id,
    loc_account_id,
    mortgage_account_id,
    fail_fast,
    dry_run,
):
    """Process all PDFs in a folder."""
    logger = ctx.obj["logger"]
    formatter = ctx.obj["formatter"]

    env_config = Config.from_env()

    if not dry_run:
        _validate_env(env_config, formatter)

        try:
            if type == "CC":
                resolved = _resolve_cc_accounts(
                    env_config.api_url,
                    env_config.api_token,
                    formatter,
                    cc_account_id=cc_account_id,
                    checking_account_id=checking_account_id,
                )
                cc_account_id = resolved["cc_account_id"]
                checking_account_id = resolved["checking_account_id"]
            else:
                resolved = _resolve_acct_accounts(
                    env_config.api_url,
                    env_config.api_token,
                    formatter,
                    checking_account_id=checking_account_id,
                    cc_account_id=cc_account_id,
                    loc_account_id=loc_account_id,
                    mortgage_account_id=mortgage_account_id,
                )
                checking_account_id = resolved["checking_account_id"]
                cc_account_id = resolved.get("cc_account_id")
                loc_account_id = resolved.get("loc_account_id")
                mortgage_account_id = resolved.get("mortgage_account_id")
        except FireflyClientError as e:
            formatter.error(f"Could not connect to Firefly-III: {e}")
            sys.exit(1)

    pdfs = sorted(Path(folder).expanduser().resolve().rglob("*.pdf"))

    if not pdfs:
        formatter.error(f"No PDF files found in {folder}")
        logger.error(f"No PDFs in folder: {folder}")
        sys.exit(1)

    logger.info(f"Found {len(pdfs)} PDF(s) in {folder}")

    results = []
    for i, pdf_path in enumerate(pdfs, 1):
        try:
            logger.info(f"[{i}/{len(pdfs)}] Processing {pdf_path.name}")

            start_date = None
            end_date = None
            if type == "ACCT":
                start_date, end_date = infer_dates_for_pdf(pdf_path)

            config = Config(
                api_url=env_config.api_url,
                api_token=env_config.api_token,
                cc_account_id=cc_account_id,
                checking_account_id=checking_account_id,
                expense_account_id=expense_account_id,
                loc_account_id=loc_account_id,
                mortgage_account_id=mortgage_account_id,
                start_date=start_date,
                end_date=end_date,
                dry_run=dry_run,
            )

            if type == "CC":
                result = _process_cc(pdf_path, config, logger, formatter)
            else:
                result = _process_acct(pdf_path, config, logger, formatter)

            results.append({"filename": pdf_path.name, "status": "success" if result["success"] else "error"})

        except Exception as e:
            logger.error(f"Failed to process {pdf_path.name}: {e}")
            results.append({"filename": pdf_path.name, "status": "error", "error": str(e)})

            if fail_fast:
                logger.info("Stopping due to error (fail-fast enabled)")
                break

    successful = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - successful

    logger.info("Batch processing complete")
    logger.info(f"  Total: {len(results)}")
    logger.info(f"  Successful: {successful}")
    logger.info(f"  Failed: {failed}")

    if failed > 0:
        sys.exit(1)


@cli.command()
@click.argument("pdf", type=click.Path(exists=True))
@click.option("--type", type=click.Choice(["CC", "ACCT"]), required=True)
@click.option("--start-date", type=str, help="Statement period start date (YYYY-MM-DD, ACCT only)")
@click.option("--end-date", type=str, help="Statement period end date (YYYY-MM-DD, ACCT only)")
@click.pass_context
def validate(ctx, pdf, type, start_date, end_date):
    """Validate PDF and show extracted data (no upload)."""
    logger = ctx.obj["logger"]
    formatter = ctx.obj["formatter"]
    pdf_path = str(Path(pdf).expanduser().resolve())

    if type == "ACCT":
        if not start_date or not end_date:
            start_date, end_date = infer_dates_for_pdf(pdf_path)
            logger.info(f"Inferred dates: {start_date} to {end_date}")

    if type == "CC":
        extractor = Extractor(pdf_path)
        result = extractor.extract()
        formatter.result(extractor.to_json(result))
    else:
        extractor = AccountExtractor(pdf_path, start_date or "", end_date or "")
        result = extractor.extract()
        formatter.result(extractor.to_json(result))

    formatter.success("Validation PASSED")


def _process_cc(pdf_path: Path, config: Config, logger, formatter: OutputFormatter) -> dict:
    """Process credit card statement."""
    formatter.info(f"Processing: {pdf_path.name}")
    formatter.verbose("Type: CC")
    formatter.verbose(f"Mode: {'DRY RUN' if config.dry_run else 'UPLOAD'}")

    extractor = Extractor(str(pdf_path))
    result = extractor.extract()
    transactions = [t.__dict__ for t in result.transactions]
    year = result.metadata.get("year", 2024)
    statement_date = result.metadata.get("statement_date")
    bonidollars_accumulated = result.metadata.get("bonidollars_accumulated")
    bonidollars_used = result.metadata.get("bonidollars_used")

    formatter.success(f"Extracted {len(transactions)} transactions")

    withdrawals, deposits, transfers = map_transactions(
        transactions=transactions,
        year=year,
        cc_account_id=config.cc_account_id,
        checking_account_id=config.checking_account_id,
        expense_account_id=config.expense_account_id,
    )

    if statement_date and (bonidollars_accumulated or bonidollars_used):
        stmt_year, stmt_month, stmt_day = statement_date
        boni_deposits, boni_withdrawals = map_bonidollars(
            accumulated=bonidollars_accumulated,
            used=bonidollars_used,
            year=stmt_year,
            month=stmt_month,
            day=stmt_day,
            cc_account_id=config.cc_account_id,
        )
        deposits.extend(boni_deposits)
        withdrawals.extend(boni_withdrawals)

    total_withdrawals = len(withdrawals)
    total_deposits = len(deposits)
    total_transfers = len(transfers)
    total_transactions = total_withdrawals + total_deposits + total_transfers

    formatter.verbose(f"  Withdrawals: {total_withdrawals}")
    formatter.verbose(f"  Deposits: {total_deposits}")
    formatter.verbose(f"  Transfers: {total_transfers}")

    if config.dry_run:
        formatter.info("[DRY RUN] Skipping upload to Firefly-III")
        result_data = {
            "filename": pdf_path.name,
            "withdrawals": total_withdrawals,
            "deposits": total_deposits,
            "transfers": total_transfers,
            "total": total_transactions,
            "dry_run": True,
        }
        formatter.result(result_data)
        return {"success": True, "data": result_data}

    formatter.info("Uploading to Firefly-III...")

    errors = []

    if withdrawals:
        formatter.verbose("Uploading withdrawals...")
        errors.extend(_send_chunks(withdrawals, f"{pdf_path.name} - Purchases", config))

    if deposits:
        formatter.verbose("Uploading deposits...")
        errors.extend(_send_chunks(deposits, f"{pdf_path.name} - Refunds", config))

    if transfers:
        formatter.verbose("Uploading transfers...")
        errors.extend(_send_chunks(transfers, f"{pdf_path.name} - Payments", config))

    if errors:
        formatter.warning(f"Completed with {len(errors)} warnings")
        for error in errors:
            formatter.warning(f"  {error}")
    else:
        formatter.success("Upload complete")

    result_data = {
        "filename": pdf_path.name,
        "withdrawals": total_withdrawals,
        "deposits": total_deposits,
        "transfers": total_transfers,
        "total": total_transactions,
        "warnings": len(errors),
        "dry_run": False,
    }

    formatter.success(f"Uploaded {total_transactions} transactions")
    formatter.result(result_data)

    return {"success": True, "data": result_data}


def _process_acct(pdf_path: Path, config: Config, logger, formatter: OutputFormatter) -> dict:
    """Process account statement."""
    formatter.info(f"Processing: {pdf_path.name}")
    formatter.verbose("Type: ACCT")
    formatter.verbose(f"Mode: {'DRY RUN' if config.dry_run else 'UPLOAD'}")

    extractor = AccountExtractor(
        str(pdf_path),
        config.start_date or "",
        config.end_date or "",
    )
    result = extractor.extract()
    year = result.metadata.get("year", 2024)

    formatter.success(f"Extracted {len(result.eop_transactions)} EOP transactions")
    formatter.verbose(f"Extracted {len(result.loc_transactions)} LoC transactions")

    withdrawals, deposits, transfers = map_account_transactions(
        eop_transactions=[t.__dict__ for t in result.eop_transactions],
        year=year,
        checking_account_id=config.checking_account_id,
        cc_account_id=config.cc_account_id,
        loc_account_id=config.loc_account_id,
        mortgage_account_id=config.mortgage_account_id,
    )

    total_withdrawals = len(withdrawals)
    total_deposits = len(deposits)
    total_transfers = len(transfers)
    total_transactions = total_withdrawals + total_deposits + total_transfers

    formatter.verbose(f"  Withdrawals: {total_withdrawals}")
    formatter.verbose(f"  Deposits: {total_deposits}")
    formatter.verbose(f"  Transfers: {total_transfers}")

    if config.dry_run:
        formatter.info("[DRY RUN] Skipping upload to Firefly-III")
        result_data = {
            "filename": pdf_path.name,
            "withdrawals": total_withdrawals,
            "deposits": total_deposits,
            "transfers": total_transfers,
            "total": total_transactions,
            "dry_run": True,
        }
        formatter.result(result_data)
        return {"success": True, "data": result_data}

    formatter.info("Uploading to Firefly-III...")

    errors = []

    if withdrawals:
        errors.extend(_send_chunks(withdrawals, f"{pdf_path.name} - Withdrawals", config))

    if deposits:
        errors.extend(_send_chunks(deposits, f"{pdf_path.name} - Deposits", config))

    if transfers:
        errors.extend(_send_chunks(transfers, f"{pdf_path.name} - Transfers", config))

    if errors:
        formatter.warning(f"Completed with {len(errors)} warnings")
        for error in errors:
            formatter.warning(f"  {error}")
    else:
        formatter.success("Upload complete")

    result_data = {
        "filename": pdf_path.name,
        "withdrawals": total_withdrawals,
        "deposits": total_deposits,
        "transfers": total_transfers,
        "total": total_transactions,
        "warnings": len(errors),
        "dry_run": False,
    }

    formatter.success(f"Uploaded {total_transactions} transactions")
    formatter.result(result_data)

    return {"success": True, "data": result_data}


def _send_chunks(transactions: list, group_title: str, config: Config) -> list:
    """Send transactions in chunks to Firefly-III."""
    errors = []
    for i in range(0, len(transactions), BATCH_CHUNK_SIZE):
        chunk = transactions[i : i + BATCH_CHUNK_SIZE]
        batch = build_batch(
            transactions=chunk,
            group_title=f"{group_title} (part {i // BATCH_CHUNK_SIZE + 1})",
            apply_rules=False,
        )
        send_batch(batch, api_url=config.api_url, api_token=config.api_token)
    return errors


if __name__ == "__main__":
    cli()
