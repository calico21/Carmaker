function res = rmainfsettxt (fname, key, txt)	% -*- Mode: Fundamental -*-
% RMAINFSETTXT - Set text key in <model>_rma.info file.
%
% This function writes a text key to the <model>_rma.info file.
%
% Returns:
%     0 on success
%    -1 on error

try
    prinf = ifile_new;
    ifile_read(prinf, fname);
    lines = splitlines(cmcmd('uenc2str', txt));
    TF = (lines == "");
    lines(TF) = [];
    ifile_settxt(prinf, key, lines);
    ifile_write(prinf, fname);
    res = 0;
catch
    res = -1;
end

if length(prinf) > 0
    ifile_delete(prinf);
end
