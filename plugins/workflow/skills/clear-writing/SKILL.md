---
name: clear-writing
description: 'Writes or revises technical text — procedures, manuals, instructions, documentation, READMEs — following ASD-STE100 Simplified Technical English principles: short sentences, active voice, one instruction per step, plain/controlled vocabulary. Use both for drafting new technical writing from scratch and for rewriting existing text to be clearer. Triggers on requests like "write this clearly," "simplify this documentation," "make this procedure easier to follow," "plain language," "STE," "simplified technical English."'
---

# Clear Writing (Simplified Technical English)

Guidance for writing or rewriting technical text so it is short, unambiguous, and easy to
translate or skim. Based on the writing-rule principles of ASD-STE100 (Simplified Technical
English), adapted here as general guidance rather than a reproduction of the licensed standard —
see "On the controlled dictionary" below.

Applies to both directions:
- **Drafting**: writing new procedures, docs, or instructions from a blank page.
- **Rewriting**: taking existing text and tightening it to these rules.

## Core rules

**One idea per sentence.** Never join two instructions or two facts with "and," "then," or a
semicolon if they can be two sentences instead. A procedure step does one thing.

**Active voice, not passive.** "Tighten the bolt," not "The bolt should be tightened." The actor
performs the action; don't hide it.

**Imperative mood for instructions.** "Open the file." Not "You should open the file" or "The
file should be opened."

**Simple tenses only.** Present tense for facts and descriptions ("The function returns a list").
Past simple for what happened. Future simple for what will happen. Avoid perfect and progressive
tenses ("has been configured," "will be running") — say what is true now or what to do now.

**Short sentences.** Target ~20 words for instructions, ~25 for descriptive/explanatory text.
If a sentence needs a comma to hold two clauses together, it is very often two sentences.

**Short paragraphs.** One topic per paragraph, generally under ~6 sentences. Break up anything
longer.

**No noun stacks.** "The user authentication configuration file" → "the file that configures
user authentication," or better, just name it directly ("the auth config file") on first mention
and reuse that name.

**No gerunds as nouns.** Avoid "the loading of the file failed" — say "the file did not load" or
"loading failed" is still acceptable as a verb form, but don't build noun phrases out of -ing
words when a plain verb sentence works.

**Use "of," not the possessive apostrophe, for technical relationships.** "The speed of the
process," not "the process's speed." (Plain possessives for people/ownership in ordinary prose
are fine — this rule is about avoiding ambiguous stacked possessives in technical description.)

**No ambiguous pronoun reference.** If "it," "this," or "that" could refer to more than one noun
in the previous sentence, replace the pronoun with the actual noun.

**Say why before what, only if needed — otherwise just say what.** Don't pad instructions with
unnecessary justification. If a step needs a reason (e.g., a safety or data-loss concern), put
the reason in its own sentence, before the instruction it explains, so the reader has context
before acting.

**No idioms, humor, or culturally-specific phrasing.** Avoid "under the hood," "at the end of the
day," rhetorical questions, sarcasm. Say the literal thing.

**No unnecessary synonyms.** Pick one term per concept and reuse it throughout a document. Don't
vary vocabulary for style ("delete," "remove," "erase" for the same action) — pick one and use it
every time.

**Spell out procedure structure explicitly.** Numbered steps for sequences that must happen in
order. Bulleted lists for unordered sets. A warning/caution that precedes the step it protects
against, on its own line, clearly marked (e.g. "**Warning:** ..." / "**Caution:** ...").

## Vocabulary

Prefer short, common, everyday words over long or Latinate ones when both mean the same thing:
"use" not "utilize," "start" not "initiate," "help" not "facilitate," "show" not "demonstrate."

Give each concept exactly one term and use it consistently — don't let "the setting," "the
option," "the parameter," and "the flag" all refer to the same thing in one document.

Prefer concrete, specific verbs over vague ones: "click," "type," "select" rather than "use" or
"do" or "handle" when a more precise word exists.

### On the controlled dictionary

The full ASD-STE100 standard also defines a fixed dictionary of ~900 approved general words, each
locked to one approved meaning and one part of speech. That dictionary is a licensed ASD
publication and is not reproduced here — don't claim output is dictionary-compliant STE. Apply
the spirit of it (few words, one meaning each, no needless synonyms) using ordinary judgment.

If the user provides a copy of the licensed dictionary or word list (e.g., as a file in this
skill's directory or pasted into the conversation), treat it as authoritative and check
vocabulary choices against it.

## Workflow

**When rewriting existing text:**
1. Read the whole passage first — don't rewrite sentence-by-sentence blind to context.
2. Rewrite following the rules above.
3. Briefly flag anything that changed meaning, not just phrasing (e.g., a hedge or qualifier that
   got dropped) — the user needs to know if simplification touched the actual content.

**When drafting new text:**
1. If the audience, purpose, or required level of formality isn't clear from context, ask rather
   than guessing — a safety procedure and a casual internal note follow the same sentence-length
   rules but very different tone.
2. Draft directly in the style described above — don't draft normally and simplify after.

**Self-check before returning output** — scan for:
- Any sentence over ~20-25 words
- Any passive-voice construction
- Any sentence doing more than one thing
- Any pronoun with an ambiguous referent
- Any term used two different ways, or two terms used for the same thing

## Example

**Before:**
> The configuration file, which is typically located in the user's home directory, should be
> edited before the application is started, and it's important that any changes that are made
> are saved prior to launching, otherwise they won't be picked up and the default settings will
> be used instead.

**After:**
> The config file is normally in your home directory. Edit it before you start the application.
> Save your changes before you start the application. If you do not save your changes, the
> application uses the default settings instead.