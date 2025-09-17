#!/usr/bin/env python3
"""
Command-line interface for claude-control
"""

import sys
import json
import time
import argparse
import logging
from pathlib import Path

from .core import (
    control,
    get_session,
    list_sessions,
    cleanup_sessions,
    FileInterface,
    _load_config,
    list_configs,
    delete_config,
    get_config,
)
from .claude_helpers import status, parallel_commands


def cmd_run(args):
    """Run a single command"""
    session = None

    try:
        session = control(args.command, timeout=args.timeout, cwd=args.cwd)

        if args.expect:
            session.expect(args.expect, timeout=args.timeout)

        if args.send:
            session.sendline(args.send)

        if args.wait:
            # Wait for process to complete
            start = time.time()
            while session.is_alive() and (time.time() - start) < args.timeout:
                time.sleep(0.1)

        output = session.get_full_output()

        if args.output:
            Path(args.output).write_text(output)
            print(f"Output saved to {args.output}")
        else:
            print(output)
    except Exception as exc:
        print(f"Error: {exc}")
        return 1
    finally:
        if session and not args.keep_alive:
            try:
                session.close()
            except Exception as close_error:
                logging.error(f"Failed to close session: {close_error}")

    return 0


def cmd_list(args):
    """List sessions"""
    sessions = list_sessions(active_only=not args.all)
    
    if args.json:
        print(json.dumps(sessions, indent=2))
    else:
        if not sessions:
            print("No active sessions")
            return 0
            
        print(f"{'ID':<20} {'Command':<30} {'Status':<10} {'PID':<8}")
        print("-" * 70)
        
        for s in sessions:
            status = "alive" if s["is_alive"] else "dead"
            pid = s.get("pid", "-")
            cmd = s["command"][:30]
            print(f"{s['session_id']:<20} {cmd:<30} {status:<10} {pid:<8}")
            
    return 0


def cmd_attach(args):
    """Attach to a session"""
    session = get_session(args.session_id)
    
    if not session:
        print(f"Session {args.session_id} not found")
        return 1
        
    if not session.is_alive():
        print(f"Session {args.session_id} is not active")
        return 1
        
    print(f"Attaching to session {args.session_id}")
    print("Press Ctrl+] to detach")
    
    try:
        session.interact()
    except KeyboardInterrupt:
        print("\nDetached from session")
        
    return 0


def cmd_investigate(args):
    """Investigate an unknown program"""
    from .investigate import investigate_program as investigate_prog
    
    print(f"Investigating {args.program}...")
    print("=" * 50)
    
    report = investigate_prog(
        program=args.program,
        timeout=args.timeout,
        safe_mode=not args.unsafe,
        save_report=not args.no_save,
    )
    
    # Print summary
    print(report.summary())
    
    if not args.no_save:
        print(f"\nDetailed report saved to: ~/.claude-control/investigations/")
    
    return 0


def cmd_probe(args):
    """Quick probe of a program"""
    from .claude_helpers import probe_interface
    
    result = probe_interface(
        program=args.program,
        timeout=args.timeout,
    )
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Program: {args.program}")
        print(f"Interactive: {result.get('interactive', False)}")
        print(f"Responsive: {result.get('responsive', False)}")
        print(f"Prompt: {result.get('prompt', 'None detected')}")
        
        if result.get('commands_found'):
            print(f"Working commands: {', '.join(result['commands_found'])}")
        
        if result.get('error'):
            print(f"Error: {result['error']}")
    
    return 0


def cmd_learn(args):
    """Learn from interactive session"""
    from .investigate import ProgramInvestigator
    
    print(f"Starting interactive learning session with {args.program}")
    print("=" * 50)
    print("Take control and demonstrate the program's features.")
    print("I'll observe and learn from your interactions.")
    print("")
    
    investigator = ProgramInvestigator(
        program=args.program,
        timeout=args.timeout,
        safe_mode=not args.unsafe,
    )
    
    report = investigator.learn_from_interaction()
    
    print("\n" + "=" * 50)
    print("Learning session complete!")
    print(f"Discovered {len(report.commands)} commands")
    print(f"Detected {len(report.prompts)} prompt patterns")
    
    if args.save:
        path = report.save()
        print(f"Report saved to: {path}")
    
    return 0


def cmd_fuzz(args):
    """Fuzz test a program"""
    from .claude_helpers import fuzz_program
    
    print(f"Fuzzing {args.program} with {args.max_inputs} inputs...")
    
    findings = fuzz_program(
        program=args.program,
        max_inputs=args.max_inputs,
        timeout=args.timeout,
    )
    
    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        print(f"\nFuzz test complete. Found {len(findings)} interesting results:")
        
        # Group by type
        by_type = {}
        for finding in findings:
            ftype = finding["type"]
            by_type.setdefault(ftype, []).append(finding)
        
        for ftype, items in by_type.items():
            print(f"\n{ftype.upper()} ({len(items)} findings):")
            for item in items[:3]:  # Show first 3 of each type
                if ftype == "error":
                    print(f"  Input: {repr(item['input'][:50])}")
                    print(f"  Output: {item['output'][:100]}")
                elif ftype == "exception":
                    print(f"  Input: {repr(item['input'][:50])}")
                    print(f"  Error: {item['error']}")
                elif ftype == "large_output":
                    print(f"  Input: {repr(item['input'][:50])}")
                    print(f"  Size: {item['output_size']} bytes")
    
    return 0


def cmd_send(args):
    """Send input to a session"""
    session = get_session(args.session_id)
    
    if not session:
        print(f"Session {args.session_id} not found")
        return 1
        
    session.sendline(args.text)
    
    if args.expect:
        try:
            session.expect(args.expect, timeout=args.timeout)
            print(session.process.before)
            if session.process.after:
                print(session.process.after)
        except Exception as e:
            print(f"Error: {e}")
            return 1
            
    return 0


def cmd_status(args):
    """Show system status"""
    info = status()
    
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print("Pexpect Bridge Status")
        print("=" * 40)
        print(f"Total sessions: {info['total_sessions']}")
        print(f"Active sessions: {info['active_sessions']}")
        print(f"Log size: {info['log_size_mb']} MB")
        print(f"Config: {info['config_path']}")
        
    return 0


def cmd_clean(args):
    """Clean up sessions"""
    if args.force:
        count = cleanup_sessions(force=True)
    else:
        count = cleanup_sessions(max_age_minutes=args.age)
        
    print(f"Cleaned up {count} sessions")
    return 0


def cmd_service(args):
    """Run as a service processing file commands"""
    print("Starting pexpect-bridge service...")
    print(f"Watching for commands in: {args.dir}")
    print("Press Ctrl+C to stop")
    
    interface = FileInterface(Path(args.dir))
    
    try:
        while True:
            interface.process_commands()
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        print("\nStopping service...")
        
    return 0


def cmd_parallel(args):
    """Run commands in parallel"""
    results = parallel_commands(args.commands, timeout=args.timeout)
    
    success_count = sum(1 for r in results.values() if r["success"])
    
    for cmd, result in results.items():
        status = "✓" if result["success"] else "✗"
        print(f"{status} {cmd}")
        
        if not result["success"] and result["error"]:
            print(f"  Error: {result['error']}")
            
    print(f"\n{success_count}/{len(results)} commands succeeded")
    
    return 0 if success_count == len(results) else 1


def cmd_config_list(args):
    """List all saved configurations"""
    configs = list_configs()
    
    if not configs:
        print("No saved configurations found")
        return 0
    
    print("Available configurations:")
    for config in configs:
        print(f"  - {config}")
    
    return 0


def cmd_config_show(args):
    """Show configuration details"""
    try:
        config = get_config(args.name)
        
        if args.json:
            print(json.dumps(config, indent=2))
        else:
            print(f"Configuration: {config['name']}")
            print(f"Command: {config['command_template']}")
            print(f"Timeout: {config.get('typical_timeout', 'default')}s")
            
            if config.get('expect_sequences'):
                print("\nExpect sequences:")
                for seq in config['expect_sequences']:
                    print(f"  Step {seq['step']}: expect '{seq['expect']}'")
                    if seq.get('note'):
                        print(f"    Note: {seq['note']}")
            
            if config.get('notes'):
                print(f"\nNotes: {config['notes']}")
    
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


def cmd_config_delete(args):
    """Delete a configuration"""
    try:
        delete_config(args.name)
        print(f"Deleted configuration '{args.name}'")
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


def main():
    """Main CLI entry point"""
    # If no arguments provided, show interactive menu
    if len(sys.argv) == 1:
        from .interactive_menu import interactive_menu
        interactive_menu()
        return 0
    
    parser = argparse.ArgumentParser(
        prog="claude-control",
        description="Give Claude control of your terminal",
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    
    parser.add_argument(
        "--menu",
        action="store_true",
        help="Show interactive menu",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # run command
    run_parser = subparsers.add_parser("run", help="Take control and run a command")
    run_parser.add_argument("command", help="Command to run")
    run_parser.add_argument("--expect", help="Pattern to expect")
    run_parser.add_argument("--send", help="Text to send after expect")
    run_parser.add_argument("--timeout", type=int, default=30, help="Timeout")
    run_parser.add_argument("--cwd", help="Working directory")
    run_parser.add_argument("--output", help="Save output to file")
    run_parser.add_argument("--wait", action="store_true", help="Wait for completion")
    run_parser.add_argument("--keep-alive", action="store_true", help="Keep session alive")
    run_parser.set_defaults(func=cmd_run)
    
    # list command
    list_parser = subparsers.add_parser("list", help="List sessions")
    list_parser.add_argument("--all", action="store_true", help="Show all sessions")
    list_parser.add_argument("--json", action="store_true", help="JSON output")
    list_parser.set_defaults(func=cmd_list)
    
    # attach command
    attach_parser = subparsers.add_parser("attach", help="Attach to a session")
    attach_parser.add_argument("session_id", help="Session ID")
    attach_parser.set_defaults(func=cmd_attach)
    
    # send command
    send_parser = subparsers.add_parser("send", help="Send to a session")
    send_parser.add_argument("session_id", help="Session ID")
    send_parser.add_argument("text", help="Text to send")
    send_parser.add_argument("--expect", help="Wait for pattern after send")
    send_parser.add_argument("--timeout", type=int, default=30, help="Timeout")
    send_parser.set_defaults(func=cmd_send)
    
    # status command
    status_parser = subparsers.add_parser("status", help="Show status")
    status_parser.add_argument("--json", action="store_true", help="JSON output")
    status_parser.set_defaults(func=cmd_status)
    
    # clean command
    clean_parser = subparsers.add_parser("clean", help="Clean up sessions")
    clean_parser.add_argument("--force", action="store_true", help="Clean all sessions")
    clean_parser.add_argument("--age", type=int, default=60, help="Max age in minutes")
    clean_parser.set_defaults(func=cmd_clean)
    
    # service command
    service_parser = subparsers.add_parser("service", help="Run as service")
    service_parser.add_argument(
        "--dir",
        default=str(Path.home() / ".claude-control"),
        help="Base directory",
    )
    service_parser.add_argument(
        "--interval",
        type=float,
        default=0.1,
        help="Poll interval",
    )
    service_parser.set_defaults(func=cmd_service)
    
    # parallel command
    parallel_parser = subparsers.add_parser("parallel", help="Run in parallel")
    parallel_parser.add_argument("commands", nargs="+", help="Commands to run")
    parallel_parser.add_argument("--timeout", type=int, default=30, help="Timeout per command")
    parallel_parser.set_defaults(func=cmd_parallel)
    
    # config command
    config_parser = subparsers.add_parser("config", help="Manage program configurations")
    config_subparsers = config_parser.add_subparsers(dest="config_command", help="Config commands")
    
    # config list
    config_list_parser = config_subparsers.add_parser("list", help="List saved configurations")
    config_list_parser.set_defaults(func=cmd_config_list)
    
    # config show
    config_show_parser = config_subparsers.add_parser("show", help="Show configuration details")
    config_show_parser.add_argument("name", help="Configuration name")
    config_show_parser.add_argument("--json", action="store_true", help="Output as JSON")
    config_show_parser.set_defaults(func=cmd_config_show)
    
    # config delete
    config_delete_parser = config_subparsers.add_parser("delete", help="Delete a configuration")
    config_delete_parser.add_argument("name", help="Configuration name")
    config_delete_parser.set_defaults(func=cmd_config_delete)
    
    # investigate command
    investigate_parser = subparsers.add_parser("investigate", help="Investigate unknown program")
    investigate_parser.add_argument("program", help="Program to investigate")
    investigate_parser.add_argument("--timeout", type=int, default=10, help="Operation timeout")
    investigate_parser.add_argument("--unsafe", action="store_true", help="Disable safety checks")
    investigate_parser.add_argument("--no-save", action="store_true", help="Don't save report")
    investigate_parser.set_defaults(func=cmd_investigate)
    
    # probe command
    probe_parser = subparsers.add_parser("probe", help="Quick probe of program interface")
    probe_parser.add_argument("program", help="Program to probe")
    probe_parser.add_argument("--timeout", type=int, default=5, help="Operation timeout")
    probe_parser.add_argument("--json", action="store_true", help="JSON output")
    probe_parser.set_defaults(func=cmd_probe)
    
    # learn command
    learn_parser = subparsers.add_parser("learn", help="Learn from interactive session")
    learn_parser.add_argument("program", help="Program to learn")
    learn_parser.add_argument("--timeout", type=int, default=10, help="Operation timeout")
    learn_parser.add_argument("--unsafe", action="store_true", help="Disable safety checks")
    learn_parser.add_argument("--save", action="store_true", help="Save learned configuration")
    learn_parser.set_defaults(func=cmd_learn)
    
    # fuzz command
    fuzz_parser = subparsers.add_parser("fuzz", help="Fuzz test a program")
    fuzz_parser.add_argument("program", help="Program to fuzz")
    fuzz_parser.add_argument("--max-inputs", type=int, default=50, help="Maximum test inputs")
    fuzz_parser.add_argument("--timeout", type=int, default=5, help="Operation timeout")
    fuzz_parser.add_argument("--json", action="store_true", help="JSON output")
    fuzz_parser.set_defaults(func=cmd_fuzz)
    
    # Parse arguments
    args = parser.parse_args()
    
    # Check for --menu flag
    if args.menu:
        from .interactive_menu import interactive_menu
        interactive_menu()
        return 0
    
    # Setup logging
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        config = _load_config()
        level_name = config.get("log_level", "INFO")
        level = getattr(logging, level_name, logging.INFO)
        unknown_level = False

        if not isinstance(level, int):
            unknown_level = True
        elif level_name != "INFO" and not hasattr(logging, level_name):
            unknown_level = True

        if unknown_level:
            if level_name != "INFO":
                logging.warning(
                    "Unknown log level '%s' in configuration. Falling back to INFO.",
                    level_name,
                )
            level = logging.INFO

        logging.basicConfig(level=level)
        
    # Run command
    if hasattr(args, "func"):
        return args.func(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())