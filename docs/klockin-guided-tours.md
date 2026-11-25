# KlockIN guided tours

Use the help button in the workspace header to open the tours available for the current page. KlockIN includes guides for Overview, My Workspace, Timekeeping, and Projects. First-time administrator setup also has a guided introduction.

Administrators can create and publish guides under **Settings → Product Tours**. Select an audience, choose a page by its Django URL name or path, and add the steps in the order you want users to see them. A blank element selector displays a centered message. KlockIN records progress per user.

Company-specific guides are scoped to their company. Built-in updates keep existing progress and preserve guides edited by administrators. Older dashboard guides point to the controls available in either the overview or the detailed reports.

The launcher uses [tours.js](../static/klockin/tours.js) and [tours.css](../static/klockin/tours.css). Its read endpoint is `/tour/api/active/`. It sends the current page path so it works after in-place navigation.

The server module lives in [klockin/tours](../klockin/tours). It keeps the existing Django application label for migration history, permissions, and recorded progress.
