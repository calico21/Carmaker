function param = cmprojectparam (section, key)
% CMPROJECTPARAM - Determine parameter of current project.
%
%   PARAM = CMPROJECTPARAM(SECTION, KEY)
%
%   Reads configuration SECTION in current project directory
%   (../Data/Config/FILE) and returns value of given KEY.
%   If KEY does not exist, an empty string is returned.

fname = sprintf('../Data/Config/%s', section);
try
    prinf = ifile_new;
    ifile_read(prinf, fname);
    param = ifile_getstr(prinf, key, '');
catch
    param = '';
end

if length(prinf) > 0
    ifile_delete(prinf);
end
