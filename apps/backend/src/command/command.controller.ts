import { Controller, Post, Body } from '@nestjs/common';
import { CommandService } from './command.service';

@Controller('commands')
export class CommandController {
  constructor(private service: CommandService) {}

  @Post('send')
  async send(@Body() body: any) {
    console.log("UI → NestJS Command:", body);
    return this.service.forwardToPython(body);
  }
}
