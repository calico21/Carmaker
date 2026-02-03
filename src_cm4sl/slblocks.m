function blkStruct = slblocks

blkStruct.OpenFcn = 'CarMaker4SL';
blkStruct.Name = sprintf('CarMaker\nfor Simulink');
blkStruct.BackgroundColor = 'orange';

if exist('CarMaker4SL') == 4
        Browser(1).Library = 'CarMaker4SL';
        Browser(1).Name    = 'CarMaker4SL';
        blkStruct.Browser = Browser;
end;

