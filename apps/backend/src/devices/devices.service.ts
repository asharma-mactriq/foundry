import { Injectable } from '@nestjs/common';
import { PrismaService } from '../common/prisma.service';

@Injectable()
export class DevicesService {
  constructor(private prisma: PrismaService) {}

  async listAll() {
    return this.prisma.device.findMany({
      include: { components: true },
      orderBy: { createdAt: 'desc' },
    });
  }

  async getById(id: string) {
    return this.prisma.device.findUnique({
      where: { id },
      include: { components: true },
    });
  }

  async create(data: { name: string; type: string }) {
    return this.prisma.device.create({ data });
  }
}
