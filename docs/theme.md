# UI Theme

The legacy UI theme (`modules.layout.theme.load_theme`) is deprecated. The FastAPI
experience uses the CSS assets in `static/css/` and is the only supported UI surface.

## Extending the theme

Avoid adding new legacy theme rules. Update the FastAPI styles in `static/css/` instead.

Example:

```css
button[kind="primary"] {
    background-color: #004080;
}

h1 {
    color: #004080;
}
```

Running `load_theme()` automatically applies the updated styles across all pages.
