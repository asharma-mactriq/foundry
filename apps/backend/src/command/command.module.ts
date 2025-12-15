import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { CommandController } from './command.controller';
import { CommandService } from './command.service';
import { CommandAckController } from './command-ack.controller';
import { CommandGateway } from 'src/gateways/command.gateway';

@Module({
  imports: [HttpModule],
  controllers: [CommandController, CommandAckController],
  providers: [CommandService, CommandGateway],
  exports: [CommandGateway]
})
export class CommandModule {}
