function CarMaker_Select(hDlg, hSrc)

% Declare model reference compliance

slConfigUISetVal(hDlg,hSrc,'ModelReferenceCompliant','on');
slConfigUISetEnabled(hDlg,hSrc,'ModelReferenceCompliant',false);
