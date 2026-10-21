-- Experimental until this installed Mac application passes the runtime fixture.
-- argv are file paths; no user input is evaluated as AppleScript source.
on run argv
    set inputPath to item 1 of argv
    set pdfPath to item 2 of argv
    set savedPath to item 3 of argv
    set tokenName to "lotra-owned-edit-" & item 4 of argv
    set ownedDoc to missing value
    try
        tell application "Microsoft PowerPoint"
            open POSIX file inputPath
            set ownedDoc to active presentation
            -- Identity is checked before any write/close. Never act on another user's document.
            if (full name of ownedDoc as text) does not end with (name of (info for POSIX file inputPath)) then error "Owned presentation identity mismatch"
            if pdfPath is not "" then save ownedDoc in POSIX file pdfPath as save as PDF
            if savedPath is not "" then
                save ownedDoc in POSIX file savedPath as save as Open XML presentation
                set oldName to name of shape 1 of slide 1 of ownedDoc
                set name of shape 1 of slide 1 of ownedDoc to tokenName
                save ownedDoc
                close ownedDoc saving no
                set ownedDoc to missing value
                open POSIX file savedPath
                set ownedDoc to active presentation
                if (full name of ownedDoc as text) does not end with (name of (info for POSIX file savedPath)) then error "Reopened presentation identity mismatch"
                if name of shape 1 of slide 1 of ownedDoc is not tokenName then error "Native edit did not survive save/reopen"
                set name of shape 1 of slide 1 of ownedDoc to oldName
                save ownedDoc
            end if
            close ownedDoc saving no
            set ownedDoc to missing value
        end tell
        return "PASS"
    on error messageText number messageNumber
        if ownedDoc is not missing value then
            try
                tell application "Microsoft PowerPoint" to close ownedDoc saving no
            end try
        end if
        error messageText number messageNumber
    end try
end run
