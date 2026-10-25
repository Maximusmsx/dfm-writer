program CompatProbe;

{$APPTYPE CONSOLE}

uses
  Windows, SysUtils, Classes, Controls, Forms, StdCtrls;

var
  Input: TFileStream;
  Binary: TMemoryStream;
  Form: TForm;
  I: Integer;
  Memo: TMemo;
  OutputDir: string;
  Lines: TStringList;

begin
  try
    if ParamCount <> 2 then
      raise Exception.Create('Usage: CompatProbe.exe input.dfm output_directory');
    OutputDir := IncludeTrailingBackslash(ParamStr(2));
    ForceDirectories(OutputDir);
    Application.Initialize;
    RegisterClass(TMemo);
    Input := TFileStream.Create(ParamStr(1), fmOpenRead or fmShareDenyWrite);
    try
      Binary := TMemoryStream.Create;
      try
        ObjectTextToBinary(Input, Binary);
        Binary.Position := 0;
        Form := TForm.CreateNew(nil);
        try
          Binary.ReadComponent(Form);
          for I := 0 to Form.ComponentCount - 1 do
            if Form.Components[I] is TMemo then
            begin
              Memo := TMemo(Form.Components[I]);
              Lines := TStringList.Create;
              try
                Lines.Assign(Memo.Lines);
                Lines.SaveToFile(OutputDir + Memo.Name + '.txt');
              finally
                Lines.Free;
              end;
            end;
        finally
          Form.Free;
        end;
      finally
        Binary.Free;
      end;
    finally
      Input.Free;
    end;
{$IFDEF VER130}
    WriteLn('PASS Delphi 5 ObjectTextToBinary + TMemo loading');
{$ENDIF}
{$IFDEF VER150}
    WriteLn('PASS Delphi 7 ObjectTextToBinary + TMemo loading');
{$ENDIF}
    ExitCode := 0;
  except
    on E: Exception do
    begin
      WriteLn(E.ClassName + ': ' + E.Message);
      ExitCode := 1;
    end;
  end;
end.
