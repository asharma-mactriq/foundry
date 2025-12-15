import { Module } from '@nestjs/common';
import { ComponentsService } from './components.service';
import { ComponentsController } from './components.controller';

@Module({
  providers: [ComponentsService],
  controllers: [ComponentsController]
})
export class ComponentsModule {}
