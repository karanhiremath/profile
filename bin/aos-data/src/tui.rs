use crate::daily;
use crate::inbox;
use crate::search;
use crate::vault::Vault;
use anyhow::Result;
use chrono::Local;
use crossterm::{
    event::{self, Event, KeyCode, KeyEventKind},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::prelude::*;
use ratatui::widgets::{Block, Borders, List, ListItem, Paragraph, Tabs};
use std::io::stdout;
use std::time::Duration;

enum View {
    Daily,
    Inbox,
    Search,
    Status,
}

pub fn run(vault: &Vault) -> Result<()> {
    enable_raw_mode()?;
    let mut out = stdout();
    execute!(out, EnterAlternateScreen)?;
    let mut term = Terminal::new(CrosstermBackend::new(out))?;
    let mut view = View::Daily;
    let mut selected = 0usize;
    let mut query = String::new();
    let mut filter = false;
    let mut status = String::new();

    let res = loop {
        let date = Local::now().date_naive();
        let daily_path = vault.daily_path(date).ok();
        let daily_preview = daily_path
            .as_ref()
            .and_then(|p| std::fs::read_to_string(p).ok())
            .unwrap_or_else(|| "(no daily yet — press n to create)".into());
        let items = inbox::list(vault).unwrap_or_default();
        let hits = if query.is_empty() {
            Vec::new()
        } else {
            search::search(vault, &query, 80).unwrap_or_default()
        };

        term.draw(|f| {
            let chunks = Layout::default()
                .direction(Direction::Vertical)
                .constraints([
                    Constraint::Length(3),
                    Constraint::Min(4),
                    Constraint::Length(2),
                ])
                .split(f.area());
            let titles = ["daily", "inbox", "search", "status"];
            let tab = match view {
                View::Daily => 0,
                View::Inbox => 1,
                View::Search => 2,
                View::Status => 3,
            };
            f.render_widget(
                Tabs::new(titles.iter().copied())
                    .select(tab)
                    .block(Block::default().borders(Borders::ALL).title(format!(
                        "aos-data {} · {}",
                        vault.argv0,
                        vault.root.display()
                    ))),
                chunks[0],
            );
            match view {
                View::Daily => {
                    f.render_widget(
                        Paragraph::new(daily_preview)
                            .wrap(ratatui::widgets::Wrap { trim: false })
                            .block(Block::default().borders(Borders::ALL).title("today")),
                        chunks[1],
                    );
                }
                View::Inbox => {
                    let rows: Vec<ListItem> = items
                        .iter()
                        .map(|i| ListItem::new(i.name.as_str()))
                        .collect();
                    f.render_widget(
                        List::new(rows)
                            .highlight_style(Style::default().add_modifier(Modifier::REVERSED))
                            .block(Block::default().borders(Borders::ALL).title("inbox")),
                        chunks[1],
                    );
                }
                View::Search => {
                    let rows: Vec<ListItem> = hits
                        .iter()
                        .map(|h| ListItem::new(format!("{}:{}  {}", h.path, h.line, h.text)))
                        .collect();
                    f.render_widget(
                        List::new(rows).block(Block::default().borders(Borders::ALL).title(
                            format!("search /{query}"),
                        )),
                        chunks[1],
                    );
                }
                View::Status => {
                    let text = format!(
                        "lane    ao0\nclass   {}\nname    {}\nargv0   {}\nvault   {}\ndaily   {}\ninbox   {} ({} files)\nmanifest {}",
                        vault.manifest.class.as_str(),
                        vault.manifest.name,
                        vault.argv0,
                        vault.root.display(),
                        daily_path
                            .as_ref()
                            .map(|p| p.display().to_string())
                            .unwrap_or_default(),
                        vault.manifest.paths.inbox,
                        items.len(),
                        vault
                            .manifest_path
                            .as_ref()
                            .map(|p| p.display().to_string())
                            .unwrap_or_else(|| "builtin".into()),
                    );
                    f.render_widget(
                        Paragraph::new(text)
                            .block(Block::default().borders(Borders::ALL).title("status")),
                        chunks[1],
                    );
                }
            }
            let hint = if filter {
                format!("/{query}  (enter apply · esc cancel)")
            } else {
                format!(
                    "1-4 views · / search · n daily · enter open · q quit  {status}"
                )
            };
            f.render_widget(Paragraph::new(hint), chunks[2]);
        })?;

        if !event::poll(Duration::from_millis(200))? {
            continue;
        }
        let Event::Key(k) = event::read()? else {
            continue;
        };
        if k.kind != KeyEventKind::Press {
            continue;
        }
        if filter {
            match k.code {
                KeyCode::Esc => {
                    filter = false;
                    query.clear();
                }
                KeyCode::Enter => filter = false,
                KeyCode::Backspace => {
                    query.pop();
                }
                KeyCode::Char(c) => query.push(c),
                _ => {}
            }
            continue;
        }
        match k.code {
            KeyCode::Char('q') | KeyCode::Esc => break Ok(()),
            KeyCode::Char('1') => view = View::Daily,
            KeyCode::Char('2') => view = View::Inbox,
            KeyCode::Char('3') => view = View::Search,
            KeyCode::Char('4') => view = View::Status,
            KeyCode::Tab => {
                view = match view {
                    View::Daily => View::Inbox,
                    View::Inbox => View::Search,
                    View::Search => View::Status,
                    View::Status => View::Daily,
                };
            }
            KeyCode::Char('/') => {
                view = View::Search;
                filter = true;
            }
            KeyCode::Char('n') => match daily::ensure(vault, date) {
                Ok(p) => status = p.display().to_string(),
                Err(e) => status = e.to_string(),
            },
            KeyCode::Char('j') | KeyCode::Down => selected = selected.saturating_add(1),
            KeyCode::Char('k') | KeyCode::Up => selected = selected.saturating_sub(1),
            KeyCode::Enter => {
                let path = match view {
                    View::Daily => daily_path.clone(),
                    View::Inbox => items.get(selected.min(items.len().saturating_sub(1))).map(|i| {
                        std::path::PathBuf::from(&i.path)
                    }),
                    View::Search => hits.get(selected.min(hits.len().saturating_sub(1))).map(|h| {
                        vault.root.join(&h.path)
                    }),
                    View::Status => None,
                };
                if let Some(p) = path {
                    restore()?;
                    let _ = crate::open::editor(&p);
                    setup()?;
                    term = Terminal::new(CrosstermBackend::new(stdout()))?;
                }
            }
            _ => {}
        }
    };

    restore()?;
    res
}

fn setup() -> Result<()> {
    enable_raw_mode()?;
    execute!(stdout(), EnterAlternateScreen)?;
    Ok(())
}

fn restore() -> Result<()> {
    disable_raw_mode()?;
    execute!(stdout(), LeaveAlternateScreen)?;
    Ok(())
}
