import {
  Controller,
  Get,
  Post,
  Param,
  Body,
} from '@nestjs/common';
import { DevicesService } from './devices.service';

@Controller('devices')
export class DevicesController {
  constructor(private devicesService: DevicesService) {}

  // GET /devices
  @Get()
  async getAll() {
    return this.devicesService.listAll();
  }

  // GET /devices/:id
  @Get(':id')
  async getById(@Param('id') id: string) {
    return this.devicesService.getById(id);
  }

  // POST /devices
  @Post()
  async create(@Body() body: { name: string; type: string }) {
    return this.devicesService.create(body);
  }
}
