import { Injectable } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { lastValueFrom } from 'rxjs';

@Injectable()
export class CommandService {
  constructor(private http: HttpService) {}

  async forwardToPython(cmd: any) {
    const res$ = this.http.post("http://localhost:8000/commands/dispatch", cmd);
    const res = await lastValueFrom(res$);
    return res.data;
  }
}
