"""
CLI entry point for Intune Packager.

Provides commands for packaging, uploading, and reporting.
"""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from . import __version__
from .config import get_config, ConfigurationError
from .installer import InstallerDetector, MetadataExtractor, IntuneWrapper
from .intune import IntuneAuth, IntuneUploader
from .reports import ReportGenerator

console = Console()


def print_banner():
    """Print application banner."""
    console.print(Panel.fit(
        "[bold blue]Intune Packager[/bold blue]\n"
        f"[dim]Enterprise Software Packaging Automation v{__version__}[/dim]",
        border_style="blue"
    ))


@click.group()
@click.option('--config', '-c', 'config_path', help='Path to configuration file')
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx, config_path):
    """
    Intune Packager - Enterprise Software Packaging Automation
    
    Automates the lifecycle of software packaging for Microsoft Intune deployment.
    """
    ctx.ensure_object(dict)
    
    try:
        ctx.obj['config'] = get_config(config_path)
    except ConfigurationError as e:
        console.print(f"[red]Configuration Error:[/red] {e}")
        sys.exit(1)


@cli.command()
@click.argument('installer_path', type=click.Path(exists=True))
@click.option('--output', '-o', 'output_dir', help='Output directory for .intunewin file')
@click.pass_context
def package(ctx, installer_path, output_dir):
    """
    Package an installer (EXE/MSI) to .intunewin format.
    
    INSTALLER_PATH: Path to the installer file
    """
    print_banner()
    console.print(f"\n[bold]Packaging:[/bold] {installer_path}\n")
    
    # Detect and analyze installer
    with console.status("[bold blue]Analyzing installer..."):
        try:
            detector = InstallerDetector(installer_path)
            info = detector.get_info()
            
            metadata_extractor = MetadataExtractor(installer_path)
            metadata = metadata_extractor.extract()
        except Exception as e:
            console.print(f"[red]Error analyzing installer:[/red] {e}")
            sys.exit(1)
    
    # Display info
    table = Table(title="Installer Information", show_header=False)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    
    table.add_row("File", info.filename)
    table.add_row("Type", info.type.value.upper())
    table.add_row("Size", f"{info.size:,} bytes")
    table.add_row("MD5", info.md5_hash)
    
    if metadata.product_name:
        table.add_row("Product", metadata.product_name)
    if metadata.manufacturer:
        table.add_row("Manufacturer", metadata.manufacturer)
    if metadata.product_version:
        table.add_row("Version", metadata.product_version)
    
    console.print(table)
    console.print()
    
    # Package the installer
    with console.status("[bold blue]Creating .intunewin package..."):
        wrapper = IntuneWrapper()
        result = wrapper.package(installer_path, output_dir)
    
    if result.success:
        console.print(f"[green][OK] Package created successfully![/green]")
        console.print(f"  Output: [bold]{result.intunewin_path}[/bold]")
        console.print(f"  Size: {result.package_size:,} bytes")
        
        # Save to history
        reporter = ReportGenerator()
        reporter.create_record(
            app_name=metadata.product_name or info.filename,
            status="packaged",
            source_file=str(info.path),
            package_file=str(result.intunewin_path),
            version=metadata.product_version,
        )
    else:
        console.print(f"[red][FAIL] Packaging failed:[/red] {result.error_message}")
        sys.exit(1)


@cli.command()
@click.argument('intunewin_path', type=click.Path(exists=True))
@click.option('--name', '-n', required=True, help='Application display name')
@click.option('--version', '-v', 'app_version', help='Application version')
@click.option('--publisher', '-p', help='Publisher name')
@click.option('--description', '-d', help='Application description')
@click.option('--install-cmd', help='Install command line')
@click.option('--uninstall-cmd', help='Uninstall command line')
@click.pass_context
def upload(ctx, intunewin_path, name, app_version, publisher, description, install_cmd, uninstall_cmd):
    """
    Upload a .intunewin package to Microsoft Intune.
    
    INTUNEWIN_PATH: Path to the .intunewin file
    """
    print_banner()
    console.print(f"\n[bold]Uploading:[/bold] {intunewin_path}\n")
    
    # Validate Azure configuration
    try:
        ctx.obj['config'].validate_azure_config()
    except ConfigurationError as e:
        console.print(f"[red]Azure Configuration Error:[/red] {e}")
        console.print("\nPlease configure Azure AD credentials in config.yaml:")
        console.print("  azure:")
        console.print("    tenant_id: YOUR_TENANT_ID")
        console.print("    client_id: YOUR_CLIENT_ID")
        console.print("    client_secret: YOUR_CLIENT_SECRET")
        sys.exit(1)
    
    # Authenticate
    with console.status("[bold blue]Authenticating with Azure AD..."):
        try:
            auth = IntuneAuth()
            auth.validate_credentials()
            console.print("[green][OK] Authentication successful[/green]")
        except Exception as e:
            console.print(f"[red]Authentication failed:[/red] {e}")
            sys.exit(1)
    
    # Upload
    uploader = IntuneUploader(auth=auth)
    
    console.print()
    result = uploader.upload(
        intunewin_path=intunewin_path,
        display_name=name,
        description=description or name,
        publisher=publisher or ctx.obj['config'].get("app_defaults.publisher", ""),
        install_command=install_cmd or f'"{Path(intunewin_path).stem}" /S',
        uninstall_command=uninstall_cmd or "",
        version=app_version or "",
    )
    
    console.print()
    
    if result.success:
        console.print("[green][OK] Upload completed successfully![/green]")
        console.print(f"  App ID: [bold]{result.app_id}[/bold]")
        console.print(f"  Upload time: {result.upload_time_seconds:.1f}s")
        
        # Save to history
        reporter = ReportGenerator()
        reporter.create_record(
            app_name=name,
            status="success",
            app_id=result.app_id,
            package_file=intunewin_path,
            version=app_version,
            upload_time_seconds=result.upload_time_seconds,
            publisher=publisher,
        )
    else:
        console.print(f"[red][FAIL] Upload failed:[/red] {result.error_message}")
        
        # Save failure to history
        reporter = ReportGenerator()
        reporter.create_record(
            app_name=name,
            status="failed",
            package_file=intunewin_path,
            version=app_version,
            error_message=result.error_message,
        )
        sys.exit(1)


@cli.command()
@click.argument('installer_path', type=click.Path(exists=True))
@click.option('--name', '-n', help='Application display name (auto-detect if not specified)')
@click.option('--version', '-v', 'app_version', help='Application version')
@click.option('--publisher', '-p', help='Publisher name')
@click.option('--output', '-o', 'output_dir', help='Output directory for .intunewin file')
@click.pass_context
def deploy(ctx, installer_path, name, app_version, publisher, output_dir):
    """
    Full deployment pipeline: package installer and upload to Intune.
    
    INSTALLER_PATH: Path to the installer file (EXE/MSI)
    """
    print_banner()
    console.print(f"\n[bold]Full Deployment Pipeline[/bold]\n")
    console.print(f"Source: {installer_path}\n")
    
    # Step 1: Analyze
    console.print("[bold cyan]Step 1/3: Analyzing installer...[/bold cyan]")
    
    try:
        detector = InstallerDetector(installer_path)
        info = detector.get_info()
        
        metadata_extractor = MetadataExtractor(installer_path)
        metadata = metadata_extractor.extract()
        
        # Use auto-detected values if not provided
        name = name or metadata.product_name or info.filename
        app_version = app_version or metadata.product_version
        publisher = publisher or metadata.manufacturer
        
        console.print(f"  Product: {name}")
        console.print(f"  Version: {app_version or 'Unknown'}")
        console.print(f"  Publisher: {publisher or 'Unknown'}")
        console.print()
    except Exception as e:
        console.print(f"[red]Error analyzing installer:[/red] {e}")
        sys.exit(1)
    
    # Step 2: Package
    console.print("[bold cyan]Step 2/3: Creating .intunewin package...[/bold cyan]")
    
    wrapper = IntuneWrapper()
    package_result = wrapper.package(installer_path, output_dir)
    
    if not package_result.success:
        console.print(f"[red]Packaging failed:[/red] {package_result.error_message}")
        sys.exit(1)
    
    console.print(f"  Package: {package_result.intunewin_path}")
    console.print()
    
    # Step 3: Upload
    console.print("[bold cyan]Step 3/3: Uploading to Intune...[/bold cyan]")
    
    try:
        ctx.obj['config'].validate_azure_config()
        auth = IntuneAuth()
        auth.validate_credentials()
    except Exception as e:
        console.print(f"[red]Azure configuration error:[/red] {e}")
        console.print("\n[yellow]Package was created successfully. You can upload it later with:[/yellow]")
        console.print(f"  intune_packager upload \"{package_result.intunewin_path}\" --name \"{name}\"")
        sys.exit(1)
    
    uploader = IntuneUploader(auth=auth)
    upload_result = uploader.upload(
        intunewin_path=str(package_result.intunewin_path),
        display_name=name,
        publisher=publisher or ctx.obj['config'].get("app_defaults.publisher", ""),
        install_command=metadata.install_command or f'"{Path(installer_path).name}" /S',
        uninstall_command=metadata.uninstall_command or "",
        version=app_version or "",
    )
    
    console.print()
    
    if upload_result.success:
        console.print(Panel.fit(
            f"[green][OK] Deployment Complete![/green]\n\n"
            f"App Name: [bold]{name}[/bold]\n"
            f"App ID: [bold]{upload_result.app_id}[/bold]\n"
            f"Total Time: {upload_result.upload_time_seconds:.1f}s",
            title="Success",
            border_style="green"
        ))
        
        # Save to history
        reporter = ReportGenerator()
        reporter.create_record(
            app_name=name,
            status="success",
            app_id=upload_result.app_id,
            source_file=str(info.path),
            package_file=str(package_result.intunewin_path),
            version=app_version,
            upload_time_seconds=upload_result.upload_time_seconds,
            publisher=publisher,
        )
    else:
        console.print(f"[red][FAIL] Upload failed:[/red] {upload_result.error_message}")
        sys.exit(1)


@cli.command()
@click.option('--format', '-f', 'output_format', default='html',
              type=click.Choice(['html', 'csv', 'json']),
              help='Report format')
@click.option('--output', '-o', 'output_path', help='Output file path')
@click.option('--open', 'open_report', is_flag=True, help='Open report after generation')
@click.pass_context
def report(ctx, output_format, output_path, open_report):
    """
    Generate deployment reports.
    """
    print_banner()
    console.print(f"\n[bold]Generating {output_format.upper()} Report[/bold]\n")
    
    reporter = ReportGenerator()
    records = reporter.get_records()
    stats = reporter.get_statistics()
    
    # Show stats
    table = Table(title="Deployment Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    
    table.add_row("Total Deployments", str(stats["total_deployments"]))
    table.add_row("Successful", f"[green]{stats['successful_deployments']}[/green]")
    table.add_row("Failed", f"[red]{stats['failed_deployments']}[/red]")
    table.add_row("Avg Upload Time", f"{stats['avg_upload_time']}s")
    
    console.print(table)
    console.print()
    
    # Generate report
    try:
        output_path = reporter.generate(output_format, output_path)
        console.print(f"[green][OK] Report generated:[/green] {output_path}")
        
        if open_report and output_format == "html":
            import webbrowser
            webbrowser.open(f"file://{output_path.absolute()}")
    except Exception as e:
        console.print(f"[red]Failed to generate report:[/red] {e}")
        sys.exit(1)


@cli.command()
@click.argument('app_id')
@click.pass_context
def status(ctx, app_id):
    """
    Check deployment status of an app in Intune.
    
    APP_ID: The Intune application ID
    """
    print_banner()
    console.print(f"\n[bold]Checking Status:[/bold] {app_id}\n")
    
    try:
        ctx.obj['config'].validate_azure_config()
        auth = IntuneAuth()
        from .intune import GraphClient
        client = GraphClient(auth)
        
        with console.status("[bold blue]Fetching app details..."):
            app = client.get_app(app_id)
            assignments = client.get_app_assignments(app_id)
        
        # Display app info
        table = Table(title="Application Details", show_header=False)
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        
        table.add_row("Display Name", app.get("displayName", "N/A"))
        table.add_row("Publisher", app.get("publisher", "N/A"))
        table.add_row("Version", app.get("version", "N/A"))
        table.add_row("Created", app.get("createdDateTime", "N/A"))
        table.add_row("Last Modified", app.get("lastModifiedDateTime", "N/A"))
        
        console.print(table)
        console.print()
        
        # Display assignments
        if assignments:
            assign_table = Table(title="Assignments")
            assign_table.add_column("Target")
            assign_table.add_column("Intent")
            
            for assignment in assignments:
                target = assignment.get("target", {})
                target_type = target.get("@odata.type", "").split(".")[-1]
                intent = assignment.get("intent", "N/A")
                assign_table.add_row(target_type, intent)
            
            console.print(assign_table)
        else:
            console.print("[yellow]No assignments configured[/yellow]")
            
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@cli.command()
@click.argument('installer_path', type=click.Path(exists=True))
def info(installer_path):
    """
    Display detailed information about an installer.
    
    INSTALLER_PATH: Path to the installer file
    """
    print_banner()
    console.print(f"\n[bold]Installer Analysis:[/bold] {installer_path}\n")
    
    try:
        detector = InstallerDetector(installer_path)
        info = detector.get_info()
        
        metadata_extractor = MetadataExtractor(installer_path)
        metadata = metadata_extractor.extract()
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    
    # File info
    table = Table(title="File Information", show_header=False)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    
    table.add_row("File", info.filename)
    table.add_row("Type", info.type.value.upper())
    table.add_row("Size", f"{info.size:,} bytes")
    table.add_row("Path", str(info.path))
    table.add_row("MD5", info.md5_hash)
    table.add_row("SHA256", info.sha256_hash)
    
    console.print(table)
    console.print()
    
    # Metadata
    meta_table = Table(title="Extracted Metadata", show_header=False)
    meta_table.add_column("Property", style="cyan")
    meta_table.add_column("Value")
    
    if metadata.product_name:
        meta_table.add_row("Product Name", metadata.product_name)
    if metadata.product_version:
        meta_table.add_row("Product Version", metadata.product_version)
    if metadata.file_version:
        meta_table.add_row("File Version", metadata.file_version)
    if metadata.manufacturer:
        meta_table.add_row("Manufacturer", metadata.manufacturer)
    if metadata.description:
        meta_table.add_row("Description", metadata.description)
    if metadata.install_command:
        meta_table.add_row("Install Command", metadata.install_command)
    if metadata.uninstall_command:
        meta_table.add_row("Uninstall Command", metadata.uninstall_command)
    
    console.print(meta_table)
    console.print()
    
    # Suggested silent switches
    console.print("[bold]Suggested Silent Install Commands:[/bold]")
    for cmd in metadata_extractor.suggest_silent_switches():
        console.print(f"  • {cmd}")


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
