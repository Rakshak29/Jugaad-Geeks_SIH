# tests/test_rag_storage_format.py
"""Confluence storage format -> clean text + sections."""

from backend.rag.confluence.storage_format import (
    parse_storage_format,
    sections_to_text,
    storage_to_text,
)

RUNBOOK = """
<p>Lead-in before any heading.</p>
<h2>Prerequisites</h2>
<ul><li>Access to the acmepay-wal S3 bucket</li></ul>
<h2>Point-In-Time Recovery</h2>
<p>Stop the server, then restore:</p>
<ac:structured-macro ac:name="code">
  <ac:parameter ac:name="language">bash</ac:parameter>
  <ac:plain-text-body><![CDATA[pg_ctl stop -D /var/lib/pgsql/data
  restore_command = 'aws s3 cp s3://bucket/%f %p']]></ac:plain-text-body>
</ac:structured-macro>
<h3>Verification</h3>
<p>Check that replay advances.</p>
"""


def test_splits_on_author_headings():
    sections = parse_storage_format(RUNBOOK)
    headings = [s.heading for s in sections]
    assert headings == [None, "Prerequisites", "Point-In-Time Recovery", "Verification"]
    # Lead-in text before the first heading is kept, not discarded.
    assert "Lead-in" in sections[0].text


def test_heading_levels_are_preserved():
    sections = parse_storage_format(RUNBOOK)
    by_heading = {s.heading: s.level for s in sections}
    assert by_heading["Prerequisites"] == 2
    assert by_heading["Verification"] == 3
    assert by_heading[None] == 0


def test_macro_parameters_are_dropped_but_rich_text_is_kept():
    body = """
        <ac:structured-macro ac:name="info">
          <ac:parameter ac:name="title">Heads up</ac:parameter>
          <ac:rich-text-body><p>Verify the WAL archive is current.</p></ac:rich-text-body>
        </ac:structured-macro>
    """
    text = storage_to_text(body)
    assert "Verify the WAL archive is current." in text
    # The macro's configuration parameters are not prose and must not leak in.
    assert "Heads up" not in text
    assert "ac:parameter" not in text


def test_cdata_code_blocks_survive_with_indentation():
    """Runbook value is in the commands -- and their indentation is meaningful."""
    sections = parse_storage_format(RUNBOOK)
    pitr = next(s for s in sections if s.heading == "Point-In-Time Recovery")
    assert "pg_ctl stop -D /var/lib/pgsql/data" in pitr.text
    assert "  restore_command =" in pitr.text


def test_source_indentation_is_flattened_in_prose():
    """XHTML source indentation must not show up as ragged text in the package."""
    body = """
        <p>If promotion fails, restore from the WAL archive
           and replay to the last known good LSN.</p>
    """
    text = storage_to_text(body)
    assert "\n and replay" not in text
    assert "and replay to the last known good LSN." in text


def test_tables_render_readably():
    body = "<table><tr><th>Step</th><th>Owner</th></tr><tr><td>Restore</td><td>DBA</td></tr></table>"
    text = storage_to_text(body)
    assert "Step" in text and "Owner" in text and "Restore" in text and "DBA" in text


def test_empty_and_malformed_bodies_do_not_raise():
    assert parse_storage_format("") == []
    assert parse_storage_format(None) == []
    # Unclosed tags must degrade, never crash a sync.
    assert isinstance(parse_storage_format("<p>dangling <b>text"), list)


def test_sections_to_text_round_trip():
    sections = parse_storage_format(RUNBOOK)
    text = sections_to_text(sections)
    assert "Prerequisites" in text
    assert "Check that replay advances." in text
